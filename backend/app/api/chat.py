from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os

from app.core import storage
from app.services.chat_service import process_query_v2
from app.api.auth import get_current_user

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatRequest(BaseModel):
    dataset_id: str
    query: str
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    conversation_id: str
    query: str
    intent: Dict[str, Any]
    generated_code: str
    code_explanation: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    chart: Optional[Dict[str, Any]] = None
    insight: str
    error: Optional[str] = None
    stdout: Optional[str] = None
    diff: Optional[Dict[str, Any]] = None

@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request = None, user: Dict[str, Any] = Depends(get_current_user)):
    # Billing quota check (only when CLOUD)
    try:
        if os.getenv("CLOUD","false").lower() in ("true","1","yes"):
            from app.core.billing import can_query
            ws = user.get("workspace_id") or "default"
            ok, msg = can_query(ws)
            if not ok:
                raise HTTPException(status_code=402, detail=msg)
    except HTTPException:
        raise
    except:
        pass
    meta = storage.get_dataset_meta(req.dataset_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    if len(req.query) > 5000:
        raise HTTPException(status_code=400, detail="Query too long (max 5000 chars)")
    # Queue check: large dataset or forecast or REDIS_URL present and long query -> 202
    try:
        est_rows = meta.get("rows", 0)
        should_queue = False
        if est_rows > 1_000_000:
            should_queue = True
        if "forecast" in req.query.lower():
            should_queue = True
        if os.getenv("REDIS_URL") and len(req.query) > 500:
            should_queue = True
        if should_queue and os.getenv("REDIS_URL"):
            import uuid
            from app.worker import run_chat_task, celery_app
            job_id = str(uuid.uuid4())[:8]
            try:
                from app.worker import _save_job
                _save_job(job_id, {"job_id": job_id, "status": "queued", "dataset_id": req.dataset_id, "query": req.query})
            except:
                pass
            try:
                run_chat_task.delay(job_id, req.dataset_id, req.query)
            except Exception:
                result = await process_query_v2(req.dataset_id, req.query, req.conversation_id)
                # billing increment
                try:
                    if os.getenv("CLOUD","false").lower() in ("true","1","yes"):
                        from app.core.billing import increment_query
                        increment_query(user.get("workspace_id") or "default")
                except:
                    pass
                return ChatResponse(**result)
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=202, content={"job_id": job_id, "status":"queued", "poll": f"/api/jobs/{job_id}"})
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        pass
    try:
        result = await process_query_v2(req.dataset_id, req.query, req.conversation_id)
        # BF-03 X-Cache header for HIT <5ms
        _is_hit = result.pop("_cache_hit", None) if isinstance(result, dict) else None
        if _is_hit:
            from fastapi.responses import JSONResponse
            return JSONResponse(content=ChatResponse(**result).model_dump(), headers={"X-Cache": "HIT"})
        try:
            if os.getenv("CLOUD","false").lower() in ("true","1","yes"):
                from app.core.billing import increment_query
                increment_query(user.get("workspace_id") or "default")
        except:
            pass
        return ChatResponse(**result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

@router.get("/conversations")
async def list_conversations(
    dataset_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    convs = storage.list_conversations(dataset_id, limit=limit, offset=offset)
    return convs

@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    conv = storage.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv

@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    ok = storage.delete_conversation(conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted", "id": conversation_id}
