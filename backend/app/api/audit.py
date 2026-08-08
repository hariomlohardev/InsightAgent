from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from app.api.auth import require_role

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
async def list_audit(
    dataset_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(require_role("admin")),
):
    from app.core.audit import list_audit as core_list

    return core_list(dataset_id=dataset_id, limit=limit)
