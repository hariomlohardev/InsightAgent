import tempfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from app.core import storage
from app.core.profiling import profile_dataframe
from app.config import settings

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

@router.post("/upload", response_model=DatasetResponse)
async def upload_dataset(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type {suffix}. Allowed: {ALLOWED_EXT}")
    
    # Check size
    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File too large. Max {settings.max_upload_mb}MB")

    # Save to temp then to storage
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    
    try:
        dataset_id = storage.save_dataset(tmp_path, file.filename)
        meta = storage.get_dataset_meta(dataset_id)
        return DatasetResponse(**meta)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

@router.get("", response_model=List[DatasetResponse])
async def list_datasets():
    datasets = storage.list_datasets()
    return [DatasetResponse(**d) for d in datasets]

@router.get("/{dataset_id}", response_model=ProfileResponse)
async def get_dataset(dataset_id: str):
    meta = storage.get_dataset_meta(dataset_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = storage.load_dataset_df(dataset_id)
        profile = profile_dataframe(df)
        # Preview
        preview_df = df.head(10)
        # Convert preview to json
        from app.agent.executor import dataframe_to_json
        preview = dataframe_to_json(preview_df, max_rows=10)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to profile dataset: {str(e)}")
    
    return ProfileResponse(dataset=DatasetResponse(**meta), profile=profile, preview=preview)

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str):
    ok = storage.delete_dataset(dataset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"status": "deleted", "id": dataset_id}
