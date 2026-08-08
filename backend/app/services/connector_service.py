import uuid
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd

from app.config import get_storage_path
from app.core import storage as storage_core
from app.core.storage import _atomic_write_json
from app.core.profiling import profile_dataframe
from app.core.connectors import fetch_df, validate_sql, fetch_sqlite_df

def _connectors_dir() -> Path:
    d = get_storage_path() / "connectors"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _connector_path(cid: str) -> Path:
    return _connectors_dir() / f"{cid}.json"

def list_connectors() -> List[Dict[str, Any]]:
    out = []
    for f in _connectors_dir().glob("*.json"):
        try:
            with open(f) as jf:
                data = json.load(jf)
                out.append(data)
        except:
            continue
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out

def get_connector(cid: str) -> Optional[Dict[str, Any]]:
    p = _connector_path(cid)
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except:
        return None

def delete_connector(cid: str) -> bool:
    # Delete connector json + dataset meta symlink/dir
    ok = False
    p = _connector_path(cid)
    if p.exists():
        p.unlink()
        ok = True
    # Also delete dataset entry if exists (same id)
    d = get_storage_path() / "datasets" / cid
    if d.exists():
        import shutil
        try:
            shutil.rmtree(d)
            ok = True
        except:
            pass
    # Also cache
    try:
        cache = get_storage_path() / "connectors" / "cache" / f"{cid}.csv"
        if cache.exists():
            cache.unlink()
    except:
        pass
    return ok

def _sanitize_connector_input(kind: str, dsn: str = None, table: str = None, sheet_url: str = None) -> None:
    kind = (kind or "").lower()
    allowed = {"postgres","postgresql","mysql","sqlite","bigquery","bq","sheets","gsheets","google_sheets"}
    if kind not in allowed:
        raise ValueError(f"Unsupported kind '{kind}'. Allowed: {sorted(allowed)}")

def create_connector(kind: str, name: str = None, dsn: str = None, table: str = None, sheet_url: str = None, credentials_json: str = None) -> Dict[str, Any]:
    kind = (kind or "").lower().strip()
    if kind == "postgresql":
        kind = "postgres"
    if kind in ("gsheets","google_sheets"):
        kind = "sheets"
    if kind == "bq":
        kind = "bigquery"
    allowed = {"postgres","mysql","sqlite","bigquery","sheets"}
    if kind not in allowed:
        raise ValueError(f"Unsupported kind '{kind}'")
    if not name:
        name = f"{kind}_connector"
    if len(name) > 100:
        raise ValueError("Name too long (max 100)")
    # Kind-specific validation
    if kind in ("postgres","mysql"):
        if not dsn:
            raise ValueError(f"{kind} requires dsn (e.g., postgresql://user:pass@host/db)")
    elif kind == "sqlite":
        if not dsn:
            dsn = ":memory:"
        # dsn can be :memory: or file path; table optional
    elif kind == "sheets":
        if not sheet_url and not dsn:
            raise ValueError("sheets requires sheet_url (paste Google Sheets share link)")
        if not sheet_url:
            sheet_url = dsn
    elif kind == "bigquery":
        if not table and not dsn:
            # require at least table
            pass

    cid = str(uuid.uuid4())[:8]
    # Try to fetch sample to validate and to build profile
    connector: Dict[str, Any] = {
        "id": cid,
        "kind": kind,
        "name": name[:100],
        "dsn": dsn,
        "table": table,
        "sheet_url": sheet_url,
        "credentials_json": credentials_json,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    # For sqlite with sample_data demo: if dsn is sample_data path we can auto-setup?
    # But we rely on caller to have file.

    # Test fetch (limit 5) — if fails, still create but mark error
    sample_error = None
    try:
        df_sample = fetch_df(connector, limit=5)
        profile = profile_dataframe(df_sample)
        # Also get rows via count if possible? Use sample rows *? but we can approximate as sample len or try full count
        try:
            df_count = fetch_df(connector, limit=10000)
            rows_est = len(df_count)
            if len(df_count) == 10000:
                rows_est = 10000  # capped
        except:
            rows_est = len(df_sample)
        connector["sample_error"] = None
    except Exception as e:
        profile = {"error": str(e), "column_names": [], "numeric_columns": [], "categorical_columns": []}
        rows_est = 0
        sample_error = str(e)
        connector["sample_error"] = sample_error[:500]

    # Persist connector json
    _atomic_write_json(_connector_path(cid), connector)

    # Also create dataset entry (virtual dataset) so chat/dashboards can use dataset_id == cid
    # Create datasets/{cid}/meta.json with type=connector
    ds_dir = get_storage_path() / "datasets" / cid
    ds_dir.mkdir(parents=True, exist_ok=True)
    # For connectors, we don't have data.csv; we store meta with type connector and lineage none
    # Estimate columns from profile sample if available
    cols = profile.get("column_names", []) if isinstance(profile, dict) else []
    # If error, cols empty
    meta = {
        "id": cid,
        "original_filename": name or f"{kind}_{cid}",
        "created_at": connector["created_at"],
        "rows": int(rows_est) if 'rows_est' in locals() else 0,
        "columns": int(len(cols)),
        "column_names": [str(c) for c in cols],
        "file_path": str(ds_dir / "data.csv"),  # virtual, may not exist
        "current_version": 0,
        "type": "connector",
        "connector": connector,
        "profile": profile,
        "sample_error": sample_error,
    }
    _atomic_write_json(ds_dir / "meta.json", meta)
    # Also write versions for compatibility
    versions_dir = ds_dir / "versions"
    versions_dir.mkdir(exist_ok=True)
    _atomic_write_json(versions_dir / "versions.json", [{"version":0,"op":"create","prompt":"connector","created_at":connector["created_at"]}])
    # Try to cache sample as data.csv for fallback? We can write sample 5 rows as data.csv so load_dataset_df has something if fetch fails later
    try:
        if 'df_sample' in locals() and df_sample is not None and not df_sample.empty:
            df_sample.to_csv(ds_dir / "data.csv", index=False)
    except:
        pass

    return meta  # Return dataset-like meta so API can reuse DatasetResponse + connector info

def query_connector(cid: str, sql: str, limit: int = 500) -> Dict[str, Any]:
    connector = get_connector(cid)
    if not connector:
        raise FileNotFoundError(f"Connector {cid} not found")
    validate_sql(sql)
    df = fetch_df(connector, limit=limit, sql=sql)
    # Profile but reuse
    from app.core.profiling import profile_dataframe
    profile = profile_dataframe(df)
    from app.agent.executor import dataframe_to_json
    preview = dataframe_to_json(df.head(20), max_rows=20)
    return {"result": dataframe_to_json(df, max_rows=500), "profile": profile, "preview": preview, "rows": len(df), "columns": len(df.columns)}

def fetch_connector_df(cid: str, limit: int = 500, sql: str = None) -> pd.DataFrame:
    connector = get_connector(cid)
    if not connector:
        raise FileNotFoundError(f"Connector {cid} not found")
    if sql:
        validate_sql(sql)
    return fetch_df(connector, limit=limit, sql=sql)

def join_datasets(ids: List[str], on: str, how: str = "left") -> Dict[str, Any]:
    if len(ids) < 2 or len(ids) > 3:
        raise ValueError("Join requires 2-3 dataset ids")
    if not on or not on.strip():
        raise ValueError("Join key 'on' cannot be empty")
    how = (how or "left").lower()
    if how not in ("inner","left","right","outer"):
        raise ValueError("how must be inner|left|right|outer")
    # Load each df
    dfs = []
    metas = []
    for did in ids:
        meta = storage_core.get_dataset_meta(did)
        if not meta:
            raise FileNotFoundError(f"Dataset {did} not found")
        # Load df via storage.load_dataset_df which now handles connector types
        try:
            df = storage_core.load_dataset_df(did)
        except Exception as e:
            raise RuntimeError(f"Failed to load {did}: {e}")
        if on not in df.columns:
            raise ValueError(f"Join key '{on}' not in dataset {did} (columns: {list(df.columns)})")
        dfs.append(df)
        metas.append(meta)

    # Check for cartesian blowup warn? we just proceed

    # Try duckdb federation first
    result_df: Optional[pd.DataFrame] = None
    try:
        import duckdb
        con = duckdb.connect()
        # Register each df
        for idx, df in enumerate(dfs):
            con.register(f"df{idx}", df)
        # Build SQL: SELECT * FROM df0 <how> JOIN df1 USING ("on") [JOIN df2 USING ...]
        # Use USING to coalesce join key
        sql = f'SELECT * FROM df0 {how.upper()} JOIN df1 USING ("{on}")'
        if len(dfs) == 3:
            sql += f' {how.upper()} JOIN df2 USING ("{on}")'
        result_df = con.execute(sql).df()
        con.close()
    except Exception as e:
        # Fallback pandas
        try:
            result_df = dfs[0]
            for other in dfs[1:]:
                result_df = result_df.merge(other, on=on, how=how, suffixes=('', '_r'))
            # If duplicate columns with suffix, keep first
        except Exception as e2:
            raise RuntimeError(f"Join failed (duckdb: {e}; pandas: {e2})")

    if result_df is None or result_df.empty and len(dfs[0])>0:
        # Could be empty due to inner join; still allow
        pass
    if result_df is None:
        raise RuntimeError("Join produced no result")

    # Save as new dataset file
    # Create dataset via storage.save_dataset from temp csv
    import tempfile
    from pathlib import Path
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        result_df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)
    try:
        new_id = storage_core.save_dataset(tmp_path, f"joined_{'_'.join(ids[:2])}.csv")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    # Patch meta with lineage
    meta = storage_core.get_dataset_meta(new_id)
    if meta:
        meta["lineage"] = ids
        meta["join_on"] = on
        meta["join_how"] = how
        meta["joined_from"] = [m.get("original_filename") for m in metas]
        # Keep type file
        _atomic_write_json(get_storage_path() / "datasets" / new_id / "meta.json", meta)
    return storage_core.get_dataset_meta(new_id)
