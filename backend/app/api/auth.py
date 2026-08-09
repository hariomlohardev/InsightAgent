from fastapi import APIRouter, HTTPException, Depends, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os

from app.core import storage
from app.core import auth as auth_core
from app.core.audit import log as audit_log

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


class RegisterRequest(BaseModel):
    email: str
    password: str
    role: Optional[str] = "viewer"
    name: Optional[str] = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class ApiKeyCreate(BaseModel):
    name: Optional[str] = ""
    scopes: Optional[str] = "read"


# Dependency to get current user (or anon if AUTH_REQUIRED false)
def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    request: Request = None,
):
    auth_required = os.getenv("AUTH_REQUIRED", "false").lower() in ("true", "1", "yes")
    enterprise = os.getenv("ENTERPRISE", "false").lower() in ("true", "1", "yes")
    is_cloud = os.getenv("CLOUD", "false").lower() in ("true", "1", "yes")
    # Try api key first
    if x_api_key:
        ak = auth_core.get_api_key_by_raw(x_api_key)
        if ak:
            user = auth_core.get_user_by_id(ak["user_id"])
            if user:
                if is_cloud:
                    try:
                        from app.config import set_workspace_id

                        set_workspace_id(user.get("workspace_id") or "default")
                    except Exception:
                        pass
                return user
        # invalid key
        raise HTTPException(status_code=401, detail="Invalid API key")
    # Try bearer JWT
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    # Also check Authorization header manually if security not parsed
    if not token and request:
        auth_h = request.headers.get("Authorization", "")
        if auth_h.lower().startswith("bearer "):
            token = auth_h[7:].strip()
    if token:
        data = auth_core.decode_jwt(token)
        if not data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        user = auth_core.get_user_by_id(data.get("sub"))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        if is_cloud:
            try:
                from app.config import set_workspace_id

                ws = data.get("ws_id") or user.get("workspace_id") or "default"
                set_workspace_id(ws)
            except Exception:
                pass
        # Return fresh user with role
        return user
    # No auth provided
    if auth_required or enterprise:
        raise HTTPException(status_code=401, detail="Authentication required")
    # Least-privilege anon: viewer (read-only). Editor requires auth even when AUTH_REQUIRED=false.
    anon_ws = "default"
    if is_cloud:
        try:
            from app.config import set_workspace_id

            set_workspace_id(anon_ws)
        except Exception:
            pass
    return {
        "id": "anon",
        "email": "anon",
        "role": "viewer",
        "name": "Anonymous",
        "workspace_id": anon_ws,
    }


def require_role(*roles):
    def _dep(user: Dict[str, Any] = Depends(get_current_user)):
        if user.get("role") not in roles:
            # admin bypass: admin can do all
            if user.get("role") == "admin":
                return user
            raise HTTPException(
                status_code=403, detail=f"Role {user.get('role')} not allowed, need {roles}"
            )
        return user

    return _dep


# Seed admin on first import
try:
    auth_core.seed_admin()
except Exception:
    pass


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, request: Request):
    try:
        # Only allow register if no users yet OR requester is admin (but without auth we can't check) - for OSS, allow viewer self-register
        # If AUTH_REQUIRED is false, anyone can register as viewer; admin can change role later
        # If there are users and role requested is admin, require admin (prevent privilege escalation)
        existing = auth_core.list_users()
        requested_role = (body.role or "viewer").lower()
        if existing and requested_role == "admin":
            # Require current user is admin
            # Try to get user from request if token present
            auth_header = request.headers.get("Authorization", "")
            if auth_header.lower().startswith("bearer "):
                from app.core.auth import decode_jwt, get_user_by_id

                data = decode_jwt(auth_header[7:].strip())
                if data:
                    u = get_user_by_id(data["sub"])
                    if not u or u.get("role") != "admin":
                        raise HTTPException(
                            status_code=403, detail="Only admin can create admin users"
                        )
                else:
                    raise HTTPException(
                        status_code=401, detail="Authentication required for admin creation"
                    )
            else:
                raise HTTPException(status_code=403, detail="Only admin can create admin users")
        user = auth_core.create_user(
            body.email, body.password, role=requested_role, name=body.name or ""
        )
        audit_log("user.register", user, ip=request.client.host if request.client else "")
        # Return safe
        return {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "name": user.get("name", ""),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    user = auth_core.get_user_by_email(body.email)
    if not user or not auth_core.verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    exp_hours = int(os.getenv("JWT_EXP_HOURS", "24"))
    token = auth_core.create_jwt(user, exp_hours=exp_hours)
    audit_log("user.login", user, ip=request.client.host if request.client else "")
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "name": user.get("name", ""),
        },
    }


@router.get("/me")
async def me(user: Dict[str, Any] = Depends(get_current_user)):
    # Return user without hash
    return {
        "id": user["id"],
        "email": user.get("email"),
        "role": user.get("role"),
        "name": user.get("name", ""),
    }


@router.post("/api-key", status_code=201)
async def create_api_key(
    body: ApiKeyCreate, user: Dict[str, Any] = Depends(get_current_user), request: Request = None
):
    # Only editor/admin can create keys? Viewer could but limited
    if user.get("role") not in ("admin", "editor"):
        if user.get("id") != "anon":
            raise HTTPException(status_code=403, detail="Only editor/admin can create API keys")
        else:
            raise HTTPException(status_code=401, detail="Authentication required")
    ak = auth_core.create_api_key(user["id"], name=body.name or "", scopes=body.scopes or "read")
    audit_log("api_key.create", user, ip=request.client.host if request and request.client else "")
    # Return raw once
    return {
        "id": ak["id"],
        "name": ak["name"],
        "api_key": ak["raw"],
        "scopes": ak["scopes"],
        "created_at": ak["created_at"],
    }


@router.get("/api-key")
async def list_api_keys(user: Dict[str, Any] = Depends(get_current_user)):
    if user.get("id") == "anon":
        raise HTTPException(status_code=401, detail="Authentication required")
    keys = auth_core.list_api_keys(user_id=user["id"])
    # Don't return hashed
    return [
        {
            "id": k["id"],
            "name": k["name"],
            "scopes": k.get("scopes"),
            "created_at": k.get("created_at"),
            "user_id": k.get("user_id"),
        }
        for k in keys
    ]


@router.delete("/api-key/{key_id}")
async def delete_api_key(
    key_id: str, user: Dict[str, Any] = Depends(get_current_user), request: Request = None
):
    if user.get("id") == "anon":
        raise HTTPException(status_code=401, detail="Authentication required")
    # Check ownership unless admin
    # Find key
    found = None
    for k in auth_core.list_api_keys():
        if k["id"] == key_id or k["hashed"] == key_id:
            found = k
            break
    if not found:
        raise HTTPException(status_code=404, detail="API key not found")
    if found["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not owner")
    ok = auth_core.delete_api_key(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found")
    audit_log("api_key.delete", user, ip=request.client.host if request and request.client else "")
    return {"status": "deleted", "id": key_id}


@router.get("/users")
async def list_users(user: Dict[str, Any] = Depends(require_role("admin"))):
    users = auth_core.list_users()
    return [
        {
            "id": u["id"],
            "email": u["email"],
            "role": u["role"],
            "name": u.get("name", ""),
            "created_at": u.get("created_at"),
        }
        for u in users
    ]


@router.post("/users/{uid}/role")
async def change_role(
    uid: str,
    body: Dict[str, Any],
    user: Dict[str, Any] = Depends(require_role("admin")),
    request: Request = None,
):
    role = body.get("role")
    if role not in ("admin", "editor", "viewer"):
        raise HTTPException(status_code=400, detail="role must be admin|editor|viewer")
    updated = auth_core.update_user_role(uid, role)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    audit_log(
        "user.role_change",
        user,
        ip=request.client.host if request and request.client else "",
        extra=f"target={uid} role={role}",
    )
    return {"id": updated["id"], "email": updated["email"], "role": updated["role"]}
