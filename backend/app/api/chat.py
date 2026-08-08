from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from app.core import storage
from app.services.chat_service import process_query_v2

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

@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # Validate dataset
    meta = storage.get_dataset_meta(request.dataset_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    try:
        result = await process_query_v2(request.dataset_id, request.query, request.conversation_id)
        return ChatResponse(**result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

@router.get("/conversations")
async def list_conversations(dataset_id: Optional[str] = None):
    convs = storage.list_conversations(dataset_id)
    return convs

@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    conv = storage.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv
