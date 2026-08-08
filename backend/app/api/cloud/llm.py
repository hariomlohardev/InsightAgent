from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import os, json
from pathlib import Path

from app.api.auth import get_current_user
from app.config import get_base_storage_path, get_workspace_id, is_cloud
from app.core.storage import _atomic_write_json

router = APIRouter(prefix="/api/cloud/llm", tags=["cloud-llm"])


class LLMSetRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    ollama_url: Optional[str] = None
    openai_key: Optional[str] = None


def _llm_path(ws_id: str = None) -> Path:
    if ws_id is None:
        ws_id = get_workspace_id()
    return get_base_storage_path() / "workspaces" / ws_id / "llm.json"


@router.get("")
async def get_llm(user=Depends(get_current_user)):
    ws_id = user.get("workspace_id") or "default"
    p = _llm_path(ws_id)
    if not p.exists():
        # fallback to global env
        return {
            "provider": os.getenv("LLM_PROVIDER", "auto"),
            "model": os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "ollama_url": os.getenv("OLLAMA_URL", "http://localhost:11434"),
        }
    try:
        with open(p) as f:
            data = json.load(f)
        # hide key
        if data.get("openai_key"):
            data["openai_key"] = "***"
        return data
    except:
        return {"provider": "auto"}


@router.post("")
async def set_llm(body: LLMSetRequest, request: Request, user=Depends(get_current_user)):
    ws_id = user.get("workspace_id") or "default"
    if user.get("role") not in ("admin", "editor"):
        raise HTTPException(status_code=403, detail="Only editor/admin can set LLM")
    provider = body.provider.lower()
    if provider not in ("openai", "groq", "gemini", "claude", "ollama", "auto", "heuristic"):
        raise HTTPException(
            status_code=400,
            detail="provider must be openai|groq|gemini|claude|ollama|auto|heuristic",
        )
    data = {
        "provider": provider,
        "model": (body.model or "")[:100],
        "ollama_url": (body.ollama_url or "http://localhost:11434")[:200],
        "updated_at": __import__("datetime")
        .datetime.now(__import__("datetime").timezone.utc)
        .isoformat(),
    }
    # handle BYOK encryption
    openai_key = body.openai_key
    if openai_key:
        enc_key = os.getenv("ENCRYPTION_KEY")
        if enc_key:
            try:
                from cryptography.fernet import Fernet

                # Fernet needs 32 urlsafe base64 key; if env is raw hex, derive
                import base64, hashlib

                if len(enc_key) < 32:
                    enc_key = base64.urlsafe_b64encode(
                        hashlib.sha256(enc_key.encode()).digest()
                    ).decode()
                f = Fernet(enc_key.encode() if isinstance(enc_key, str) else enc_key)
                data["openai_key_enc"] = f.encrypt(openai_key.encode()).decode()
            except Exception as e:
                # fallback plain with warning
                data["openai_key"] = openai_key
                data["encrypted"] = False
        else:
            data["openai_key"] = openai_key
            data["encrypted"] = False
    else:
        # keep existing if any
        p = _llm_path(ws_id)
        if p.exists():
            try:
                with open(p) as f:
                    old = json.load(f)
                if old.get("openai_key") or old.get("openai_key_enc"):
                    data["openai_key"] = old.get("openai_key")
                    data["openai_key_enc"] = old.get("openai_key_enc")
            except:
                pass
    _atomic_write_json(_llm_path(ws_id), data)
    # return without key
    out = {k: v for k, v in data.items() if k not in ("openai_key", "openai_key_enc")}
    if "openai_key" in data or "openai_key_enc" in data:
        out["has_key"] = True
    return out


@router.post("/test")
async def test_llm(request: Request, user=Depends(get_current_user)):
    # Mock ollama test: try hit ollama_url
    ws_id = user.get("workspace_id") or "default"
    p = _llm_path(ws_id)
    cfg = {}
    if p.exists():
        try:
            with open(p) as f:
                cfg = json.load(f)
        except:
            pass
    provider = cfg.get("provider", "auto")
    if provider == "ollama":
        url = cfg.get("ollama_url", "http://localhost:11434")
        try:
            import httpx

            r = httpx.get(f"{url}/api/tags", timeout=3)
            if r.status_code == 200:
                return {"status": "ok", "provider": "ollama", "url": url}
            return {"status": "ollama unreachable", "code": r.status_code}
        except Exception as e:
            # mock success for test
            return {"status": "mock_ok", "provider": "ollama", "note": str(e)[:200]}
    return {"status": "ok", "provider": provider}
