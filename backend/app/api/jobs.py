from fastapi import APIRouter, HTTPException
from pathlib import Path
from app.config import get_storage_path
import json

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

def _jobs_dir():
    d = get_storage_path() / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d

@router.get("/{job_id}")
async def get_job(job_id: str):
    # Check redis cache first? but filesystem is source of truth for OSS without redis
    p = _jobs_dir() / f"{job_id}.json"
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except:
            pass
    # Try redis
    try:
        from app.core.cache import get as cache_get
        v = cache_get(f"job:{job_id}")
        if v:
            return v
    except:
        pass
    raise HTTPException(status_code=404, detail="Job not found")
