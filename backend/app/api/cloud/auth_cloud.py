from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from typing import Optional
import os, uuid, json
from datetime import datetime, timezone

from app.core import auth as auth_core
from app.api.auth import get_current_user
from app.config import get_base_storage_path

router = APIRouter(prefix="/api/cloud/auth", tags=["cloud-auth"])


class CloudRegisterRequest(BaseModel):
    email: str
    password: str
    workspace_name: str = "My Workspace"
    name: Optional[str] = ""


@router.post("/register", status_code=201)
async def cloud_register(body: CloudRegisterRequest, request: Request):
    # Create workspace + user
    ws_id = str(uuid.uuid4())[:8]
    # ensure workspace dirs
    try:
        auth_core.ensure_workspace(ws_id, name=body.workspace_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # Set context for creation
    try:
        from app.config import set_workspace_id

        set_workspace_id(ws_id)
    except Exception:
        pass
    try:
        user = auth_core.create_user(
            body.email, body.password, role="admin", name=body.name or "", workspace_id=ws_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # update workspace owner
    try:
        meta_p = get_base_storage_path() / "workspaces" / ws_id / "meta.json"
        if meta_p.exists():
            with open(meta_p) as f:
                meta = json.load(f)
            meta["owner_user_id"] = user["id"]
            meta["name"] = body.workspace_name[:50]
            from app.core.storage import _atomic_write_json

            _atomic_write_json(meta_p, meta)
    except Exception:
        pass
    token = auth_core.create_jwt(user)
    # Mock email verification: just return
    return {
        "workspace_id": ws_id,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "workspace_id": ws_id,
        },
        "access_token": token,
        "token_type": "bearer",
        "verification": "mock_sent",
    }


@router.post("/login")
async def cloud_login(body: CloudRegisterRequest, request: Request):
    # reuse existing login but ensure workspace context
    user = auth_core.get_user_by_email(body.email)
    if not user or not auth_core.verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    from app.config import set_workspace_id

    set_workspace_id(user.get("workspace_id") or "default")
    token = auth_core.create_jwt(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "workspace_id": user.get("workspace_id", "default"),
        },
        "workspace_id": user.get("workspace_id", "default"),
    }
