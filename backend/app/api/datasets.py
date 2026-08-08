import tempfile
import re
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List

from app.core import storage
from app.core.profiling import profile_dataframe
from app.config import settings
from app.services.wrangle_service import preview_clean, apply_clean
import os
from fastapi import Depends, Request
from app.core.audit import log as audit_log
from app.api.auth import get_current_user, require_role

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

ALLOWED_EXT = {".csv", ".xlsx", ".xls", ".json"}

class DatasetResponse(BaseModel):
    id: str
    original_filename: str
    rows: int
    columns: int
    column_names: List[str]
    created_at: str

class ProfileResponse(BaseModel):
    dataset: DatasetResponse
    profile: dict
    preview: dict

def _sanitize_filename(filename: str) -> str:
    """Sanitize filename: block path traversal, limit length, replace unsafe chars."""
    # Take only basename (block ../)
    name = Path(filename).name
    # Replace unsafe chars but keep alnum, dot, dash, underscore
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    # Limit length
    if len(name) > 120:
        stem = Path(name).stem[:100]
        suffix = Path(name).suffix[:20]
        name = stem + suffix
    # Ensure not empty
    if not name or name in [".", ".."]:
        name = "upload.csv"
    return name

@router.post("/upload", response_model=DatasetResponse)
async def upload_dataset(file: UploadFile = File(...), request: Request = None, user = Depends(get_current_user)):
    # L8 Billing quota check (only when CLOUD=true)
    try:
        if os.getenv("CLOUD","false").lower() in ("true","1","yes"):
            from app.core.billing import can_create_dataset
            ws = user.get("workspace_id") or "default"
            ok, msg = can_create_dataset(ws)
            if not ok:
                raise HTTPException(status_code=402, detail=msg)
    except HTTPException:
        raise
    except:
        pass
    # Validate original filename extension before sanitizing (strict)
    original_name = file.filename or "upload.csv"
    orig_suffix = Path(original_name).suffix.lower()
    if orig_suffix not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type {orig_suffix}. Allowed: {ALLOWED_EXT}")
    safe_name = _sanitize_filename(original_name)
    suffix = Path(safe_name).suffix.lower()
    # Ensure sanitized still has allowed ext, fallback to original
    if suffix not in ALLOWED_EXT:
        suffix = orig_suffix
        safe_name = Path(safe_name).stem + suffix
    
    # Streaming upload (10.2) — avoid OOM on 100MB, chunked 8KB
    max_bytes = settings.max_upload_mb * 1024 * 1024
    tmp_path = None
    try:
        # Use UploadFile.file (SpooledTemporaryFile) streaming
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)
            # Stream 8KB chunks
            size = 0
            while True:
                chunk = await file.read(8192)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    # cleanup
                    try:
                        tmp.close()
                        tmp_path.unlink(missing_ok=True)
                    except:
                        pass
                    raise HTTPException(status_code=413, detail=f"File too large. Max {settings.max_upload_mb}MB")
                tmp.write(chunk)
            # Validate not empty / whitespace
            if size == 0:
                raise HTTPException(status_code=400, detail="Empty file. Please upload a file with data.")
            # Check whitespace only via reading back first bytes
            tmp.flush()
    except HTTPException:
        raise
    except Exception as e:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except:
                pass
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")
    # Verify not whitespace only (quick check)
    try:
        with open(tmp_path, "rb") as f:
            first = f.read(8192)
            if len(first.strip()) == 0:
                # check if file only whitespace
                f.seek(0)
                rest = f.read(1024*1024)
                if len(rest.strip()) == 0:
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=400, detail="File contains only whitespace.")
    except HTTPException:
        raise
    except:
        pass
    
    try:
        try:
            dataset_id = storage.save_dataset(tmp_path, safe_name)
        except ValueError as e:
            # storage.save_dataset raises ValueError for parse errors
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            # Check if it's a parsing error
            err_msg = str(e)
            if "could not parse" in err_msg.lower() or "parser" in err_msg.lower() or "empty" in err_msg.lower():
                raise HTTPException(status_code=400, detail=f"Could not parse file: {err_msg}")
            raise HTTPException(status_code=500, detail=f"Failed to save dataset: {err_msg}")
        
        meta = storage.get_dataset_meta(dataset_id)
        if not meta:
            raise HTTPException(status_code=500, detail="Failed to create dataset metadata")
        # RBAC: viewer cannot upload
        if user.get("role") not in ("admin","editor"):
            # Need to delete dataset if already saved? But check before save would be better; for now after save, delete and 403
            storage.delete_dataset(dataset_id)
            raise HTTPException(status_code=403, detail="Viewer cannot upload datasets")
        # Owner attribution + audit
        try:
            from pathlib import Path as _P
            from app.config import get_storage_path as _gsp
            from app.core.storage import _atomic_write_json
            p = _gsp() / "datasets" / dataset_id / "meta.json"
            import json as _j
            with open(p) as jf:
                m = _j.load(jf)
            m["owner"] = user.get("id")
            _atomic_write_json(p, m)
        except:
            pass
        audit_log("dataset.upload", user, dataset_id=dataset_id, ip=request.client.host if request and request.client else "", extra=safe_name)
        return DatasetResponse(**{**meta, "owner": user.get("id")})
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

class JoinRequest(BaseModel):
    ids: List[str]
    on: str
    how: str = "left"

@router.post("/join", response_model=DatasetResponse)
async def join_datasets_endpoint(body: JoinRequest, request: Request = None, user = Depends(get_current_user)):
    if len(body.ids) < 2 or len(body.ids) > 3:
        raise HTTPException(status_code=400, detail="Join requires 2-3 dataset ids")
    if not body.on.strip():
        raise HTTPException(status_code=400, detail="Join key 'on' cannot be empty")
    if body.how.lower() not in ("inner","left","right","outer"):
        raise HTTPException(status_code=400, detail="how must be inner|left|right|outer")
    if user.get("role") not in ("admin","editor"):
        raise HTTPException(status_code=403, detail="Viewer cannot join datasets")
    try:
        from app.services.connector_service import join_datasets
        meta = join_datasets(body.ids, body.on.strip(), body.how)
        audit_log("dataset.join", user, dataset_id=",".join(body.ids), ip=request.client.host if request and request.client else "", extra=f"on={body.on} how={body.how}")
        return DatasetResponse(**meta)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=List[DatasetResponse])
async def list_datasets(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0), q: str = Query(None, description="Search by filename (ilike)")):
    datasets = storage.list_datasets(q=q) if q else storage.list_datasets()
    # Pagination
    paginated = datasets[offset:offset+limit]
    return [DatasetResponse(**d) for d in paginated]

@router.get("/{dataset_id}", response_model=ProfileResponse)
async def get_dataset(dataset_id: str, request: Request = None):
    from fastapi.responses import JSONResponse
    meta = storage.get_dataset_meta(dataset_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dataset not found")
    # Check cache for profile:version (10.2)
    version = meta.get("current_version", 0)
    try:
        from app.core.cache import get as cache_get, set as cache_set, cache_key
        ck = cache_key(f"profile:{dataset_id}:{version}")
        cached = cache_get(ck)
        if cached and isinstance(cached, dict) and "dataset" in cached:
            # Return cached with X-Cache header
            return JSONResponse(content=cached, headers={"X-Cache": "HIT"})
    except:
        pass
    # For connectors, if live fetch fails, return stored profile instead of 500
    if meta.get("type") == "connector":
        try:
            df = storage.load_dataset_df(dataset_id)
            profile = profile_dataframe(df, dataset_id=dataset_id, version=version)
            preview_df = df.head(10)
            from app.agent.executor import dataframe_to_json
            preview = dataframe_to_json(preview_df, max_rows=10)
            resp = ProfileResponse(dataset=DatasetResponse(**meta), profile=profile, preview=preview)
            # cache it
            try:
                from app.core.cache import set as cache_set, cache_key as ckf
                ck = ckf(f"profile:{dataset_id}:{version}")
                cache_set(ck, resp.model_dump(), ttl=60)
            except:
                pass
            return resp
        except Exception as e:
            profile = meta.get("profile") or {"column_names": meta.get("column_names", []), "numeric_columns": [], "categorical_columns": [], "inferred_roles": {}, "error": str(e)}
            preview = {"columns": meta.get("column_names", []), "data": [], "rows": 0, "columns_count": len(meta.get("column_names", [])), "truncated": False, "display_rows": 0}
            return ProfileResponse(dataset=DatasetResponse(**meta), profile=profile, preview=preview)
    try:
        df = storage.load_dataset_df(dataset_id)
        profile = profile_dataframe(df, dataset_id=dataset_id, version=version)
        preview_df = df.head(10)
        from app.agent.executor import dataframe_to_json
        preview = dataframe_to_json(preview_df, max_rows=10)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to profile dataset: {str(e)}")
    resp_data = ProfileResponse(dataset=DatasetResponse(**meta), profile=profile, preview=preview).model_dump()
    # Cache and return with MISS
    try:
        from app.core.cache import set as cache_set, cache_key as ckf
        ck = ckf(f"profile:{dataset_id}:{version}")
        cache_set(ck, resp_data, ttl=60)
    except:
        pass
    # Use JSONResponse to allow X-Cache header
    from fastapi.responses import JSONResponse as JR
    return JR(content=resp_data, headers={"X-Cache": "MISS"})

@router.get("/{dataset_id}/preview")
async def preview_dataset(dataset_id: str, rows: int = Query(10, ge=1, le=100)):
    meta = storage.get_dataset_meta(dataset_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = storage.load_dataset_df(dataset_id)
        from app.agent.executor import dataframe_to_json
        preview = dataframe_to_json(df.head(rows), max_rows=rows)
        return preview
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{dataset_id}/download")
async def download_dataset(dataset_id: str):
    meta = storage.get_dataset_meta(dataset_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dataset not found")
    path = storage.get_dataset_path(dataset_id)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Dataset file not found")
    return FileResponse(path, filename=meta["original_filename"], media_type="text/csv")

# Wrangling endpoints (Level 2)

class WrangleRequest(BaseModel):
    query: str
    code: str | None = None

class WranglePreviewResponse(BaseModel):
    success: bool
    code: str | None = None
    explanation: str | None = None
    diff: dict | None = None
    preview: dict | None = None
    before_preview: dict | None = None
    chart: dict | None = None
    result: dict | None = None
    error: str | None = None
    stdout: str | None = None

@router.post("/{dataset_id}/preview-clean", response_model=WranglePreviewResponse)
async def preview_clean_endpoint(dataset_id: str, body: WrangleRequest):
    meta = storage.get_dataset_meta(dataset_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        result = await preview_clean(dataset_id, body.query)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")

@router.post("/{dataset_id}/apply-clean")
async def apply_clean_endpoint(dataset_id: str, body: WrangleRequest):
    meta = storage.get_dataset_meta(dataset_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        result = await apply_clean(dataset_id, body.query, body.code)
        if not result.get("success"):
            # Return 400 for validation errors, not 500
            return result
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Apply failed: {str(e)}")

@router.get("/{dataset_id}/versions")
async def list_versions_endpoint(dataset_id: str):
    meta = storage.get_dataset_meta(dataset_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dataset not found")
    versions = storage.list_versions(dataset_id)
    return {"dataset_id": dataset_id, "current_version": meta.get("current_version", 0), "versions": versions}

@router.post("/{dataset_id}/revert")
async def revert_version_endpoint(dataset_id: str, body: dict):
    meta = storage.get_dataset_meta(dataset_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dataset not found")
    version = body.get("version")
    if version is None:
        raise HTTPException(status_code=400, detail="Missing version")
    try:
        version = int(version)
    except:
        raise HTTPException(status_code=400, detail="Invalid version")
    ok = storage.revert_to_version(dataset_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    # Return new profile
    try:
        df = storage.load_dataset_df(dataset_id)
        profile = profile_dataframe(df)
        return {"status": "reverted", "version": version, "profile": profile, "meta": storage.get_dataset_meta(dataset_id)}
    except Exception as e:
        return {"status": "reverted", "version": version}



@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str, request: Request = None, user = Depends(get_current_user)):
    if user.get("role") not in ("admin","editor"):
        raise HTTPException(status_code=403, detail="Viewer cannot delete datasets")
    ok = storage.delete_dataset(dataset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Dataset not found")
    audit_log("dataset.delete", user, dataset_id=dataset_id, ip=request.client.host if request and request.client else "")
    return {"status": "deleted", "id": dataset_id}
