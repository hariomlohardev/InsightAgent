import json
import os
import uuid
import shutil
import tempfile
import time
import threading
from pathlib import Path
from datetime import timezone, datetime
from typing import List, Dict, Any, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# --- DataFrame cache: dataset_id:version -> DataFrame (avoids re-read from disk) ---
# Memory-aware LRU: 4 entries max but also 600MB cap to prevent 10M OOM (4×800MB would OOM)
_DF_CACHE: Dict[str, pd.DataFrame] = {}
_DF_CACHE_TS: Dict[str, float] = {}
_DF_CACHE_BYTES: Dict[str, int] = {}
_DF_CACHE_TOTAL_BYTES: int = 0
_DF_CACHE_LOCK = threading.Lock()
_DF_CACHE_MAX = 4  # avoid unbounded growth
_DF_CACHE_MAX_BYTES = 600 * 1024 * 1024  # 600MB cap
_DF_CACHE_TTL = 300  # seconds
# --- list_datasets cache ---
_LIST_CACHE: Dict[str, Any] = {"data": None, "ts": 0, "q": None}
_LIST_CACHE_TTL = 2.0
_LIST_CACHE_LOCK = threading.Lock()


def _df_cache_key(dataset_id: str, version: int, use_polars: bool) -> str:
    return f"{dataset_id}:{version}:{use_polars}"


def _df_estimate_bytes(df: pd.DataFrame) -> int:
    try:
        # deep=True for object/string
        return int(df.memory_usage(deep=True).sum())
    except Exception:
        try:
            return int(df.shape[0] * df.shape[1] * 8)
        except Exception:
            return 10 * 1024 * 1024  # fallback 10MB


def _df_cache_evict_if_needed():
    global _DF_CACHE_TOTAL_BYTES
    # Evict LRU until under both count and bytes limits
    while (len(_DF_CACHE) > _DF_CACHE_MAX) or (
        _DF_CACHE_TOTAL_BYTES > _DF_CACHE_MAX_BYTES and len(_DF_CACHE) > 1
    ):
        try:
            oldest = min(_DF_CACHE_TS, key=lambda k: _DF_CACHE_TS[k])
        except Exception:
            break
        _DF_CACHE_TOTAL_BYTES -= _DF_CACHE_BYTES.pop(oldest, 0)
        _DF_CACHE.pop(oldest, None)
        _DF_CACHE_TS.pop(oldest, None)


def _invalidate_df_cache(dataset_id: str = None):
    global _DF_CACHE_TOTAL_BYTES
    with _DF_CACHE_LOCK:
        if dataset_id is None:
            _DF_CACHE.clear()
            _DF_CACHE_TS.clear()
            _DF_CACHE_BYTES.clear()
            _DF_CACHE_TOTAL_BYTES = 0
        else:
            for k in list(_DF_CACHE.keys()):
                if k.startswith(f"{dataset_id}:"):
                    _DF_CACHE_TOTAL_BYTES -= _DF_CACHE_BYTES.pop(k, 0)
                    _DF_CACHE.pop(k, None)
                    _DF_CACHE_TS.pop(k, None)


def _invalidate_list_cache():
    with _LIST_CACHE_LOCK:
        _LIST_CACHE["data"] = None
        _LIST_CACHE["ts"] = 0


from app.config import get_storage_path, get_workspace_id, is_cloud

# L09 DB dual-path helpers (graceful fallback when no DATABASE_URL)
try:
    from app.core.db import use_db as _use_db
except Exception:

    def _use_db():  # type: ignore
        return False


def _sync_db_url() -> str | None:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return None
    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql://", 1)
    return url


def _db_available() -> bool:
    try:
        return _use_db()
    except Exception:
        return False


def _db_ensure():
    try:
        from app.core.db import init_db_sync

        init_db_sync()
    except Exception:
        pass


def _db_save_meta(meta: Dict[str, Any]):
    """Insert/update dataset meta in DB when DB available. Returns True if written."""
    if not _db_available():
        return False
    try:
        _db_ensure()
        from app.core.db import get_sync_sessionmaker, DatasetRow
        from datetime import datetime as _dt

        sm = get_sync_sessionmaker()
        if sm is None:
            return False
        with sm() as s:
            # upsert
            existing = (
                s.get(DatasetRow, meta["id"])
                if hasattr(s, "get")
                else s.query(DatasetRow).get(meta["id"])
            )
            # fallback for sqlalchemy 2.0
            if existing is None:
                try:
                    existing = s.get(DatasetRow, meta["id"])
                except:
                    existing = None
            if existing:
                existing.workspace_id = meta.get("workspace_id", "default")
                existing.original_filename = meta.get("original_filename")
                existing.rows = meta.get("rows")
                existing.columns = meta.get("columns")
                existing.column_names = meta.get("column_names")
                existing.meta_json = meta
                existing.owner = meta.get("owner")
            else:
                # parse created_at
                ca = meta.get("created_at")
                try:
                    dt = _dt.fromisoformat(ca) if ca else _dt.now(timezone.utc)
                except:
                    dt = _dt.now(timezone.utc)
                row = DatasetRow(
                    id=meta["id"],
                    workspace_id=meta.get("workspace_id", "default"),
                    original_filename=meta.get("original_filename"),
                    rows=meta.get("rows"),
                    columns=meta.get("columns"),
                    column_names=meta.get("column_names"),
                    meta_json=meta,
                    created_at=dt,
                    owner=meta.get("owner"),
                )
                s.add(row)
            s.commit()
        return True
    except Exception as e:
        logger.debug(f"_db_save_meta failed: {e}")
        return False


def _db_list_metas() -> List[Dict[str, Any]] | None:
    if not _db_available():
        return None
    try:
        _db_ensure()
        from app.core.db import get_sync_sessionmaker, DatasetRow

        sm = get_sync_sessionmaker()
        if sm is None:
            return None
        with sm() as s:
            from sqlalchemy import select

            # workspace filter when CLOUD=true
            ws = get_workspace_id() if is_cloud() else None
            try:
                if ws and ws != "default":
                    stmt = (
                        select(DatasetRow)
                        .where(DatasetRow.workspace_id == ws)
                        .order_by(DatasetRow.created_at.desc())
                    )
                else:
                    # when CLOUD true but ws default, still filter by workspace_id to isolate default
                    if is_cloud():
                        stmt = (
                            select(DatasetRow)
                            .where(DatasetRow.workspace_id == ws)
                            .order_by(DatasetRow.created_at.desc())
                        )
                    else:
                        stmt = select(DatasetRow).order_by(DatasetRow.created_at.desc())
                rows = s.execute(stmt).scalars().all()
            except Exception:
                # fallback query api
                q = s.query(DatasetRow)  # type: ignore
                if is_cloud():
                    q = q.filter(DatasetRow.workspace_id == get_workspace_id())
                rows = q.order_by(DatasetRow.created_at.desc()).all()  # type: ignore
            out = []
            for r in rows:
                if r.meta_json:
                    out.append(r.meta_json)
                else:
                    out.append(
                        {
                            "id": r.id,
                            "original_filename": r.original_filename,
                            "rows": r.rows,
                            "columns": r.columns,
                            "column_names": r.column_names,
                            "created_at": r.created_at.isoformat() if r.created_at else "",
                            "owner": r.owner,
                            "workspace_id": r.workspace_id,
                        }
                    )
            return out
    except Exception as e:
        logger.debug(f"_db_list_metas failed: {e}")
        return None


def _db_get_meta(dataset_id: str) -> Dict[str, Any] | None:
    if not _db_available():
        return None
    try:
        from app.core.db import get_sync_sessionmaker, DatasetRow

        sm = get_sync_sessionmaker()
        if sm is None:
            return None
        with sm() as s:
            from sqlalchemy import select

            # Enforce workspace isolation when CLOUD=true
            ws = get_workspace_id() if is_cloud() else None
            try:
                if is_cloud():
                    stmt = select(DatasetRow).where(
                        (DatasetRow.id == dataset_id) & (DatasetRow.workspace_id == ws)
                    )
                else:
                    stmt = select(DatasetRow).where(DatasetRow.id == dataset_id)
                row = s.execute(stmt).scalar_one_or_none()
            except Exception:
                # fallback with workspace filter
                q = s.query(DatasetRow).filter_by(id=dataset_id)  # type: ignore
                if is_cloud():
                    q = q.filter_by(workspace_id=ws)
                row = q.first()  # type: ignore
            if row:
                # Enforce workspace check even for fallback
                if is_cloud() and row.workspace_id != ws:
                    return None
                if row.meta_json:
                    return row.meta_json
                return {
                    "id": row.id,
                    "original_filename": row.original_filename,
                    "rows": row.rows,
                    "columns": row.columns,
                    "column_names": row.column_names,
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                    "owner": row.owner,
                    "workspace_id": row.workspace_id,
                }
            return None
    except Exception as e:
        logger.debug(f"_db_get_meta failed: {e}")
        return None


def _db_delete_meta(dataset_id: str) -> bool | None:
    if not _db_available():
        return None
    try:
        from app.core.db import get_sync_sessionmaker, DatasetRow

        sm = get_sync_sessionmaker()
        if sm is None:
            return None
        with sm() as s:
            from sqlalchemy import select

            try:
                stmt = select(DatasetRow).where(DatasetRow.id == dataset_id)
                row = s.execute(stmt).scalar_one_or_none()
            except Exception:
                row = s.query(DatasetRow).filter_by(id=dataset_id).first()  # type: ignore
            if row:
                s.delete(row)
                s.commit()
                return True
            return False
    except Exception as e:
        logger.debug(f"_db_delete_meta failed: {e}")
        return None


def _datasets_dir() -> Path:
    d = get_storage_path() / "datasets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _conversations_dir() -> Path:
    d = get_storage_path() / "conversations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write_json(path: Path, data: Dict[str, Any], default=None):
    """Atomic write via tmp+rename."""
    tmp = path.with_suffix(".tmp")
    kwargs = {"indent": 2}
    if default:
        kwargs["default"] = default
    with open(tmp, "w") as f:
        json.dump(data, f, **kwargs)
    tmp.replace(path)


def save_dataset(file_path: Path, original_filename: str) -> str:
    """Copy file to storage and create meta. Returns dataset_id. Raises ValueError on parse errors."""
    dataset_id = str(uuid.uuid4())[:8]
    dest_dir = _datasets_dir() / dataset_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "data.csv"
    suffix = file_path.suffix.lower()

    # Handle different file types with robust error handling
    df = None
    if suffix in [".csv"]:
        # Try csv with multiple encodings and options
        last_err = None
        for encoding in ["utf-8", "utf-8-sig", "latin1"]:
            for sep in [",", ";", "\t", "|"]:
                try:
                    df = pd.read_csv(file_path, encoding=encoding, sep=sep, nrows=5)
                    # Heuristic: if only 1 column and sep != ",", try next sep
                    if (
                        len(df.columns) == 1
                        and sep == ","
                        and "," in open(file_path, encoding=encoding).read(1024)
                    ):
                        continue
                    # Successfully read preview, now read full
                    df = pd.read_csv(file_path, encoding=encoding, sep=sep)
                    break
                except Exception as e:
                    last_err = e
                    continue
            if df is not None and len(df.columns) > 0:
                break
        if df is None or df.empty and file_path.stat().st_size > 10:
            # Try one more time with default
            try:
                df = pd.read_csv(file_path)
            except Exception as e:
                raise ValueError(f"Could not parse CSV: {str(e)}")
        if df is not None:
            df.to_csv(dest_file, index=False)
        else:
            raise ValueError(f"Could not parse CSV: {last_err}")

    elif suffix in [".xlsx", ".xls"]:
        # Convert to csv for uniform handling, keep original too
        shutil.copy(file_path, dest_dir / f"original{suffix}")
        last_err = None
        # Try openpyxl for xlsx, xlrd for xls
        for engine in [None, "openpyxl", "xlrd"]:
            try:
                kwargs = {}
                if engine:
                    kwargs["engine"] = engine
                df = pd.read_excel(file_path, **kwargs)
                break
            except Exception as e:
                last_err = e
                continue
        if df is None:
            raise ValueError(f"Could not parse Excel: {last_err}")
        # Check empty
        if df.empty:
            raise ValueError("Excel file is empty or has no data rows")
        df.to_csv(dest_file, index=False)

    elif suffix in [".json"]:
        shutil.copy(file_path, dest_dir / "original.json")
        last_err = None
        # Try multiple orients
        for orient in [None, "records", "columns", "index"]:
            try:
                kwargs = {}
                if orient:
                    kwargs["orient"] = orient
                df = pd.read_json(file_path, **kwargs)
                # If successful and has data
                if not df.empty and len(df.columns) > 0:
                    break
                # Try raw json load
                if df.empty:
                    import json as _json

                    with open(file_path) as f:
                        data = _json.load(f)
                    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                        df = pd.DataFrame(data)
                        break
                    elif isinstance(data, dict):
                        # Could be {"data": [...] } or {"rows": [...]}
                        for key in ["data", "rows", "items", "records"]:
                            if key in data and isinstance(data[key], list):
                                df = pd.DataFrame(data[key])
                                break
                        if not df.empty:
                            break
            except Exception as e:
                last_err = e
                continue
        if df is None or df.empty:
            raise ValueError(f"Could not parse JSON: {last_err or 'empty or invalid format'}")
        df.to_csv(dest_file, index=False)

    else:
        # Generic
        shutil.copy(file_path, dest_file)
        try:
            df = pd.read_csv(dest_file)
        except Exception as e:
            raise ValueError(f"Unsupported file type {suffix}: {str(e)}")

    # Validate df
    if df is None:
        raise ValueError("Failed to load dataset: unknown error")
    if df.empty:
        # Allow empty but warn: create meta with 0 rows
        pass
    if len(df.columns) == 0:
        raise ValueError("File has no columns")
    if len(df.columns) > 1000:
        raise ValueError(f"Too many columns ({len(df.columns)}), max 1000")

    # Load to get shape (already have df)
    try:
        rows = len(df)
        cols = len(df.columns)
        preview_cols = df.columns.tolist()
    except Exception:
        rows, cols = 0, 0
        preview_cols = []

    meta = {
        "id": dataset_id,
        "original_filename": original_filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rows": int(rows),
        "columns": int(cols),
        "column_names": [str(c) for c in preview_cols],
        "file_path": str(dest_file),
        "current_version": 0,
        "type": "file",
        "workspace_id": get_workspace_id() if is_cloud() else "default",
    }
    _atomic_write_json(dest_dir / "meta.json", meta)

    # L09 DB dual-write
    try:
        _db_save_meta(meta)
    except Exception:
        pass
    # L09 S3 dual-write when STORAGE_BACKEND=s3
    try:
        if os.getenv("STORAGE_BACKEND", "fs") == "s3" and os.getenv("S3_BUCKET"):
            bucket = os.getenv("S3_BUCKET")
            s3_path = f"s3://{bucket}/datasets/{dataset_id}/data.csv"
            wrote = False
            # Try fsspec first (s3fs)
            try:
                import fsspec

                with fsspec.open(s3_path, mode="wt") as f:
                    df.to_csv(f, index=False)
                with fsspec.open(f"s3://{bucket}/datasets/{dataset_id}/meta.json", mode="wt") as f:
                    json.dump(meta, f)
                wrote = True
            except Exception as fe:
                logger.debug(f"S3 fsspec save failed: {fe}")
            # Fallback to boto3 (moto mock guarantees this works)
            if not wrote:
                try:
                    import boto3
                    import io

                    csv_buf = io.StringIO()
                    df.to_csv(csv_buf, index=False)
                    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
                    s3.put_object(
                        Bucket=bucket,
                        Key=f"datasets/{dataset_id}/data.csv",
                        Body=csv_buf.getvalue(),
                    )
                    s3.put_object(
                        Bucket=bucket, Key=f"datasets/{dataset_id}/meta.json", Body=json.dumps(meta)
                    )
                    wrote = True
                except Exception as be:
                    logger.debug(f"S3 boto3 save failed: {be}")
    except Exception as e:
        logger.debug(f"S3 save failed, fs fallback ok: {e}")

    # BF-04 parquet cache for re-read 60ms vs 205ms (only when >100k rows or >5MB)
    try:
        if rows > 100_000 or dest_file.stat().st_size > 5 * 1024 * 1024:
            try:
                df.to_parquet(dest_dir / "data.parquet", index=False)
            except Exception:
                try:
                    import pyarrow as pa, pyarrow.parquet as pq  # type: ignore

                    table = pa.Table.from_pandas(df)
                    pq.write_table(table, str(dest_dir / "data.parquet"))
                except Exception:
                    pass
    except Exception:
        pass

    # Create versions for L1.5 future (v0)
    versions_dir = dest_dir / "versions"
    versions_dir.mkdir(exist_ok=True)
    shutil.copy(dest_file, versions_dir / "0.csv")
    versions_meta = [
        {"version": 0, "op": "create", "prompt": "upload", "created_at": meta["created_at"]}
    ]
    _atomic_write_json(versions_dir / "versions.json", versions_meta)
    _invalidate_list_cache()
    _invalidate_df_cache(dataset_id)

    return dataset_id


def list_datasets(q: str = None) -> List[Dict[str, Any]]:
    # cached 2s to avoid scanning meta.json per request; invalidate on save/delete/upload
    if q is None:
        with _LIST_CACHE_LOCK:
            if (
                _LIST_CACHE["data"] is not None
                and (time.time() - _LIST_CACHE["ts"]) < _LIST_CACHE_TTL
            ):
                # return copy
                return list(_LIST_CACHE["data"])
    # L10 search: filter by filename ilike when q provided
    # L09 DB path first when DATABASE_URL set
    # Try DB filtered query first
    if q and _db_available():
        try:
            _db_ensure()
            from app.core.db import get_sync_sessionmaker, DatasetRow
            from sqlalchemy import select

            sm = get_sync_sessionmaker()
            if sm is not None:
                with sm() as s:
                    # ilike on original_filename
                    try:
                        # Use ilike for postgres, like for sqlite (case-insensitive)
                        stmt = select(DatasetRow).where(
                            DatasetRow.original_filename.ilike(f"%{q}%")
                        )
                        rows = s.execute(stmt).scalars().all()
                    except Exception:
                        # fallback to python filter
                        rows = s.execute(select(DatasetRow)).scalars().all()
                        rows = [r for r in rows if q.lower() in (r.original_filename or "").lower()]
                    out = [
                        (
                            r.meta_json
                            if r.meta_json
                            else {
                                "id": r.id,
                                "original_filename": r.original_filename,
                                "rows": r.rows,
                                "columns": r.columns,
                                "column_names": r.column_names,
                                "created_at": r.created_at.isoformat() if r.created_at else "",
                            }
                        )
                        for r in rows
                    ]
                    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                    return out
        except Exception as e:
            logger.debug(f"DB search failed, fallback: {e}")
            pass
    db_metas = _db_list_metas()
    if db_metas is not None:
        # Merge + filter by q if needed
        if q:
            ql = q.lower()
            db_metas = [m for m in db_metas if ql in (m.get("original_filename", "") or "").lower()]
        else:
            # Merge DB + filesystem (DB is source of truth when enabled, but keep fs fallback for legacy)
            fs_ids = set()
            try:
                fs_metas = []
                for d in _datasets_dir().iterdir():
                    if d.is_dir():
                        mf = d / "meta.json"
                        if mf.exists():
                            try:
                                with open(mf) as f:
                                    data = json.load(f)
                                if (
                                    d / "data.csv" in [Path(data.get("file_path", ""))]
                                    or (d / "data.csv").exists()
                                ):
                                    fs_metas.append(data)
                                    fs_ids.add(data.get("id"))
                            except:
                                continue
                db_ids = {m.get("id") for m in db_metas}
                for m in fs_metas:
                    if m.get("id") not in db_ids:
                        # also filter by q if provided (already handled, but merge case is q=None here)
                        db_metas.append(m)
            except Exception:
                pass
            db_metas.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return db_metas
        db_metas.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        # also cache DB path
        if not q:
            with _LIST_CACHE_LOCK:
                _LIST_CACHE["data"] = list(db_metas)
                _LIST_CACHE["ts"] = time.time()
        return db_metas
    datasets = []
    datasets = []
    for d in _datasets_dir().iterdir():
        if d.is_dir():
            meta_file = d / "meta.json"
            if meta_file.exists():
                try:
                    with open(meta_file) as f:
                        data = json.load(f)
                    # L10 search filter
                    if q and q.lower() not in (data.get("original_filename", "") or "").lower():
                        continue
                    try:
                        fp = d / "data.csv"
                        if fp.exists() and not os.access(fp, os.R_OK):
                            continue
                    except Exception:
                        pass
                    datasets.append(data)
                except json.JSONDecodeError:
                    continue
                except (PermissionError, OSError):
                    continue
    datasets.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    # cache q=None result
    if q is None:
        with _LIST_CACHE_LOCK:
            _LIST_CACHE["data"] = list(datasets)
            _LIST_CACHE["ts"] = time.time()
    return datasets


def get_dataset_meta(dataset_id: str) -> Optional[Dict[str, Any]]:
    # L09 DB first
    dbm = _db_get_meta(dataset_id)
    if dbm is not None:
        return dbm
    # If DB enabled but miss, try S3 meta when STORAGE_BACKEND=s3
    if _db_available() and os.getenv("STORAGE_BACKEND", "fs") == "s3" and os.getenv("S3_BUCKET"):
        try:
            import fsspec, json as _j

            bucket = os.getenv("S3_BUCKET")
            with fsspec.open(f"s3://{bucket}/datasets/{dataset_id}/meta.json", mode="rt") as f:
                return _j.load(f)
        except Exception:
            pass
    # If DB was enabled and returned None, but we have filesystem fallback, still check fs (for legacy datasets not yet in DB)
    meta_file = _datasets_dir() / dataset_id / "meta.json"
    if not meta_file.exists():
        # When DB enabled and miss, return None to signal not found (avoid fs leak across workspaces)
        if _db_available():
            # Check fs as migration fallback before giving up
            if not meta_file.exists():
                return None
        else:
            return None
    try:
        with open(meta_file) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def get_dataset_path(dataset_id: str) -> Optional[Path]:
    meta = get_dataset_meta(dataset_id)
    if not meta:
        return None
    p = Path(meta["file_path"])
    if p.exists():
        return p
    alt = _datasets_dir() / dataset_id / "data.csv"
    if alt.exists():
        return alt
    return None


def load_dataset_df(dataset_id: str, use_polars: bool = None) -> pd.DataFrame:
    global _DF_CACHE_TOTAL_BYTES
    # cache check — stable key dataset_id:version (not id(df))
    # determine version early for cache key
    try:
        _meta_for_cache = get_dataset_meta(dataset_id)
        _ver = _meta_for_cache.get("current_version", 0) if _meta_for_cache else 0
    except Exception:
        _ver = 0
    # resolve use_polars for cache key (auto-enable for large files)
    _up = use_polars
    if _up is None:
        # auto: enable polars by default and for large files; respects explicit false only when small
        env = os.getenv("USE_POLARS", "true").lower() in ("true", "1", "yes")
        # for large files always try polars even if env false (unless explicitly disabled via USE_POLARS=false and small)
        _up = env
    _ck = _df_cache_key(dataset_id, _ver, bool(_up))
    with _DF_CACHE_LOCK:
        _cached_df = _DF_CACHE.get(_ck)
        _ts = _DF_CACHE_TS.get(_ck, 0)
        if _cached_df is not None and (time.time() - _ts) < _DF_CACHE_TTL:
            # return copy to prevent mutation of cached object
            try:
                return _cached_df.copy(deep=False)
            except Exception:
                return _cached_df
    # L09 S3 primary when STORAGE_BACKEND=s3, fallback to fs
    storage_backend = os.getenv("STORAGE_BACKEND", "fs")
    if storage_backend == "s3":
        bucket = os.getenv("S3_BUCKET", "")
        if bucket:
            # Try fsspec first
            try:
                import fsspec

                s3_path = f"s3://{bucket}/datasets/{dataset_id}/data.csv"
                with fsspec.open(s3_path, mode="rt") as f:
                    return pd.read_csv(f)
            except Exception as e:
                logger.debug(f"S3 fsspec load failed: {e}")
            # Fallback to boto3
            try:
                import boto3, io

                s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
                obj = s3.get_object(Bucket=bucket, Key=f"datasets/{dataset_id}/data.csv")
                body = obj["Body"].read().decode("utf-8")
                return pd.read_csv(io.StringIO(body))
            except Exception as e:
                logger.debug(f"S3 boto3 load failed, fs fallback: {e}")
                pass
    # Handle connector virtual datasets
    meta = get_dataset_meta(dataset_id)
    if meta and meta.get("type") == "connector":
        try:
            from app.services.connector_service import fetch_connector_df

            return fetch_connector_df(dataset_id, limit=5000)
        except Exception as e:
            p_fallback = _datasets_dir() / dataset_id / "data.csv"
            if p_fallback.exists():
                try:
                    return pd.read_csv(p_fallback)
                except:
                    pass
            raise
    p = get_dataset_path(dataset_id)
    if not p or not p.exists():
        raise FileNotFoundError(f"Dataset {dataset_id} not found")
    # Polars fast path — default true, auto for large files (fix #6)
    # use_polars already resolved for cache key in _up; reuse that
    if use_polars is None:
        # _up already computed; but keep backward-compat env check
        use_polars = os.getenv("USE_POLARS", "true").lower() in ("true", "1", "yes")
        # auto-enable for large files (>5MB or >100k rows) even if env false
        try:
            if not use_polars:
                fsize = p.stat().st_size if p.exists() else 0
                if fsize > 5 * 1024 * 1024:
                    use_polars = True
                else:
                    _meta = get_dataset_meta(dataset_id)
                    if _meta and _meta.get("rows", 0) > 100_000:
                        use_polars = True
        except:
            pass
    if use_polars:
        _polars_df = None
        try:
            import polars as pl

            pq = p.parent / "data.parquet"
            if pq.exists():
                try:
                    df_pl = pl.scan_parquet(str(pq)).collect()
                    _polars_df = df_pl.to_pandas()
                except Exception:
                    try:
                        _polars_df = pd.read_parquet(pq)
                    except Exception:
                        pass
                if _polars_df is not None:
                    with _DF_CACHE_LOCK:
                        # memory-aware eviction
                        b = _df_estimate_bytes(_polars_df)
                        _DF_CACHE[_ck] = _polars_df
                        _DF_CACHE_TS[_ck] = time.time()
                        _DF_CACHE_BYTES[_ck] = b
                        _DF_CACHE_TOTAL_BYTES += b
                        _df_cache_evict_if_needed()
                    return _polars_df.copy(deep=True) if hasattr(_polars_df, "copy") else _polars_df
            try:
                df_pl = pl.scan_csv(str(p), infer_schema_length=1000, try_parse_dates=True).collect(
                    streaming=True
                )
                _polars_df = df_pl.to_pandas()
            except TypeError as e:
                if "streaming" in str(e).lower() or "unexpected" in str(e).lower():
                    df_pl = pl.scan_csv(str(p), infer_schema_length=1000).collect()
                    _polars_df = df_pl.to_pandas()
                else:
                    raise
            except Exception:
                try:
                    df_pl = pl.scan_csv(str(p), infer_schema_length=1000).collect()
                    _polars_df = df_pl.to_pandas()
                except Exception:
                    try:
                        df_pl = pl.read_csv(str(p), try_parse_dates=True, infer_schema_length=1000)
                        _polars_df = df_pl.to_pandas()
                    except:
                        pass
            if _polars_df is not None:
                with _DF_CACHE_LOCK:
                    b = _df_estimate_bytes(_polars_df)
                    _DF_CACHE[_ck] = _polars_df
                    _DF_CACHE_TS[_ck] = time.time()
                    _DF_CACHE_BYTES[_ck] = b
                    _DF_CACHE_TOTAL_BYTES += b
                    _df_cache_evict_if_needed()
                return _polars_df.copy(deep=True) if hasattr(_polars_df, "copy") else _polars_df
        except ImportError:
            pass
    # Fallback pandas with chunked sample for huge files (avoid OOM)
    _df = None
    try:
        # If file >50MB, avoid single pd.read_csv spike — use polars if available, else chunked
        fsize = p.stat().st_size if p.exists() else 0
        if fsize > 50 * 1024 * 1024 and not use_polars:
            chunks = []
            for chunk in pd.read_csv(p, chunksize=100000):
                chunks.append(chunk)
                if sum(len(c) for c in chunks) > 10_000_000:
                    break
            if chunks:
                _df = pd.concat(chunks, ignore_index=True)
            else:
                _df = pd.read_csv(p)
        else:
            _df = pd.read_csv(p)
    except Exception:
        orig_xlsx = p.parent / "original.xlsx"
        orig_xls = p.parent / "original.xls"
        if orig_xlsx.exists():
            _df = pd.read_excel(orig_xlsx)
        elif orig_xls.exists():
            _df = pd.read_excel(orig_xls)
        else:
            raise
    # store in cache (dataset_id:version -> df) — memory-aware
    if _df is not None:
        try:
            with _DF_CACHE_LOCK:
                b = _df_estimate_bytes(_df)
                _DF_CACHE[_ck] = _df
                _DF_CACHE_TS[_ck] = time.time()
                _DF_CACHE_BYTES[_ck] = b
                _DF_CACHE_TOTAL_BYTES += b
                _df_cache_evict_if_needed()
        except Exception:
            pass
    return _df


def delete_dataset(dataset_id: str) -> bool:
    # L09 DB first
    db_res = _db_delete_meta(dataset_id)
    # S3 cleanup
    if os.getenv("STORAGE_BACKEND", "fs") == "s3" and os.getenv("S3_BUCKET"):
        try:
            import fsspec

            bucket = os.getenv("S3_BUCKET")
            s3_path = f"s3://{bucket}/datasets/{dataset_id}/data.csv"
            fs = fsspec.filesystem("s3")
            if fs.exists(s3_path):
                fs.rm(s3_path, recursive=True)
            # meta
            try:
                fs.rm(f"s3://{bucket}/datasets/{dataset_id}/meta.json")
            except:
                pass
        except Exception as e:
            logger.debug(f"S3 delete failed: {e}")
    # Also handle connector cleanup
    try:
        meta = get_dataset_meta(dataset_id)  # after DB delete, will fallback to fs
        if meta and meta.get("type") == "connector":
            try:
                from app.config import get_storage_path as _gsp

                c_path = _gsp() / "connectors" / f"{dataset_id}.json"
                if c_path.exists():
                    c_path.unlink()
            except:
                pass
    except:
        pass
    d = _datasets_dir() / dataset_id
    existed = d.exists()
    _invalidate_df_cache(dataset_id)
    _invalidate_list_cache()
    # also invalidate profile cache via cache module if available
    try:
        from app.core.cache import delete as cache_delete, cache_key

        meta_tmp = (
            get_dataset_meta(dataset_id) if False else None
        )  # placeholder to avoid import loop; delete below via version loop
        # delete profile keys for this dataset (version 0..current+5)
        for v in range(20):
            try:
                cache_delete(cache_key(f"profile:{dataset_id}:{v}"))
            except:
                pass
    except:
        pass
    if d.exists():
        try:
            shutil.rmtree(d)
            if db_res is not None:
                return True  # DB handled, fs cleaned
            return True
        except (PermissionError, OSError):
            try:
                import stat

                for root, dirs, files in os.walk(d):
                    for f in files:
                        try:
                            os.chmod(os.path.join(root, f), stat.S_IWUSR | stat.S_IRUSR)
                        except:
                            pass
                shutil.rmtree(d)
                return True
            except:
                return bool(db_res)
    # If DB deleted and fs didn't exist, still success
    if db_res:
        return True
    return False if not existed else True


# Conversations with L1.5 polish: quota, pagination, delete, atomic

MAX_CONVERSATIONS_PER_DATASET = 50


def save_conversation_message(
    dataset_id: str, conversation_id: str, role: str, content: Dict[str, Any]
) -> str:
    """Append message to conversation file. Returns conversation_id. Atomic write."""
    if not conversation_id:
        conversation_id = str(uuid.uuid4())[:8]
    conv_file = _conversations_dir() / f"{conversation_id}.json"
    if conv_file.exists():
        try:
            with open(conv_file) as f:
                conv = json.load(f)
        except json.JSONDecodeError:
            conv = {
                "id": conversation_id,
                "dataset_id": dataset_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "messages": [],
            }
    else:
        conv = {
            "id": conversation_id,
            "dataset_id": dataset_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "messages": [],
        }
    msg = {"role": role, "timestamp": datetime.now(timezone.utc).isoformat(), **content}
    conv["messages"].append(msg)
    conv["updated_at"] = datetime.now(timezone.utc).isoformat()
    conv["dataset_id"] = dataset_id  # ensure

    def _default(o):
        import numpy as np

        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        return str(o)

    _atomic_write_json(conv_file, conv, default=_default)

    # Enforce quota: keep only last 50 conversations per dataset (LRU)
    try:
        convs = list_conversations(dataset_id)
        if len(convs) > MAX_CONVERSATIONS_PER_DATASET:
            # Delete oldest
            to_delete = sorted(convs, key=lambda x: x.get("updated_at", ""))[
                : len(convs) - MAX_CONVERSATIONS_PER_DATASET
            ]
            for c in to_delete:
                f = _conversations_dir() / f"{c['id']}.json"
                if f.exists():
                    f.unlink()
    except Exception:
        pass

    return conversation_id


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    f = _conversations_dir() / f"{conversation_id}.json"
    if not f.exists():
        return None
    try:
        with open(f) as fv:
            return json.load(fv)
    except json.JSONDecodeError:
        try:
            f.unlink()
        except:
            pass
        return None


def list_conversations(
    dataset_id: Optional[str] = None, limit: int = 100, offset: int = 0
) -> List[Dict[str, Any]]:
    convs = []
    for f in _conversations_dir().glob("*.json"):
        try:
            with open(f) as fv:
                c = json.load(fv)
        except json.JSONDecodeError:
            try:
                f.unlink()
            except:
                pass
            continue
        except Exception:
            continue
        if dataset_id is None or c.get("dataset_id") == dataset_id:
            convs.append(c)
    convs.sort(key=lambda x: x.get("updated_at", x.get("created_at", "")), reverse=True)
    # Pagination
    return convs[offset : offset + limit]


def delete_conversation(conversation_id: str) -> bool:
    f = _conversations_dir() / f"{conversation_id}.json"
    if f.exists():
        f.unlink()
        return True
    return False


# Versions helpers for L2 but prepared
def list_versions(dataset_id: str) -> List[Dict[str, Any]]:
    vfile = _datasets_dir() / dataset_id / "versions" / "versions.json"
    if not vfile.exists():
        return []
    try:
        with open(vfile) as f:
            return json.load(f)
    except:
        return []


def get_version_path(dataset_id: str, version: int) -> Optional[Path]:
    p = _datasets_dir() / dataset_id / "versions" / f"{version}.csv"
    if p.exists():
        return p
    return None


def create_version(dataset_id: str, df: pd.DataFrame, op: str, prompt: str, code: str) -> int:
    """Save df as new version, update versions.json and meta.current_version. Returns new version number. Max 20 versions."""
    max_versions = 20
    dest_dir = _datasets_dir() / dataset_id
    versions_dir = dest_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    vfile = versions_dir / "versions.json"

    # Load existing
    versions = list_versions(dataset_id)
    next_version = (max([v["version"] for v in versions]) + 1) if versions else 1
    if versions and next_version == 0:
        next_version = 1

    # Save df
    dest_file = versions_dir / f"{next_version}.csv"
    df.to_csv(dest_file, index=False)
    # Also update main data.csv
    main_file = dest_dir / "data.csv"
    df.to_csv(main_file, index=False)

    # Update versions.json
    new_entry = {
        "version": next_version,
        "op": op,
        "prompt": prompt[:200],
        "code": code[:1000],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
    }
    versions.append(new_entry)
    # Enforce max 20 (keep v0 + last 19)
    if len(versions) > max_versions:
        # Keep v0 and most recent
        v0 = [v for v in versions if v["version"] == 0]
        rest = [v for v in versions if v["version"] != 0]
        rest.sort(key=lambda x: x["version"])
        # Keep last max_versions-1 (since v0 is extra)
        rest = rest[-(max_versions - 1) :]
        versions = sorted(v0 + rest, key=lambda x: x["version"])
        # Delete old files
        keep_versions = {v["version"] for v in versions}
        for f in versions_dir.glob("*.csv"):
            try:
                ver = int(f.stem)
                if ver not in keep_versions:
                    f.unlink()
            except:
                pass

    _atomic_write_json(vfile, versions)

    # Update meta
    meta = get_dataset_meta(dataset_id)
    if meta:
        meta["current_version"] = next_version
        meta["rows"] = int(df.shape[0])
        meta["columns"] = int(df.shape[1])
        meta["column_names"] = [str(c) for c in df.columns.tolist()]
        _atomic_write_json(dest_dir / "meta.json", meta)
        # invalidate caches on version bump
        _invalidate_df_cache(dataset_id)
        _invalidate_list_cache()
        try:
            from app.core.cache import delete as cache_delete, cache_key

            for v in [next_version, next_version - 1]:
                try:
                    cache_delete(cache_key(f"profile:{dataset_id}:{v}"))
                except:
                    pass
            # also chat cache: chat:{id}:*:*
            # leave chat cache to expire via ttl (60s) or version key already isolates
        except:
            pass
        # update parquet cache for fast re-read
        try:
            if int(df.shape[0]) > 100_000:
                try:
                    df.to_parquet(dest_dir / "data.parquet", index=False)
                except:
                    pass
        except:
            pass

    return next_version


def revert_to_version(dataset_id: str, version: int) -> bool:
    """Revert data.csv to versions/{version}.csv, update meta.current_version. Returns success."""
    v_path = get_version_path(dataset_id, version)
    if not v_path or not v_path.exists():
        return False
    dest_dir = _datasets_dir() / dataset_id
    main_file = dest_dir / "data.csv"
    try:
        df = pd.read_csv(v_path)
    except Exception:
        # Try to copy directly if read fails
        shutil.copy(v_path, main_file)
        meta = get_dataset_meta(dataset_id)
        if meta:
            meta["current_version"] = version
            _atomic_write_json(dest_dir / "meta.json", meta)
            _invalidate_df_cache(dataset_id)
            _invalidate_list_cache()
        return True

    df.to_csv(main_file, index=False)
    # Also save as new version? No, just revert pointer
    meta = get_dataset_meta(dataset_id)
    if meta:
        meta["current_version"] = version
        meta["rows"] = int(df.shape[0])
        meta["columns"] = int(df.shape[1])
        meta["column_names"] = [str(c) for c in df.columns.tolist()]
        _atomic_write_json(dest_dir / "meta.json", meta)
        _invalidate_df_cache(dataset_id)
        _invalidate_list_cache()
        try:
            from app.core.cache import delete as cache_delete, cache_key

            for v in range(20):
                try:
                    cache_delete(cache_key(f"profile:{dataset_id}:{v}"))
                except:
                    pass
        except:
            pass
    return True
