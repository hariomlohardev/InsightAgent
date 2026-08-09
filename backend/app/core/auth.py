import os
import secrets
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import json

from app.config import get_storage_path
from app.core.storage import _atomic_write_json

JWT_ALG = "HS256"


def _jwt_secret() -> str:
    # Prefer env
    sec = os.getenv("JWT_SECRET")
    if sec:
        return sec
    # Persisted file
    p = get_storage_path() / "jwt_secret"
    if p.exists():
        try:
            return p.read_text().strip()
        except:
            pass
    # Generate
    new_sec = secrets.token_urlsafe(32)
    try:
        p.write_text(new_sec)
    except:
        pass
    return new_sec


def _users_dir() -> Path:
    d = get_storage_path() / "users"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _api_keys_dir() -> Path:
    d = get_storage_path() / "api_keys"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _user_path(uid: str) -> Path:
    return _users_dir() / f"{uid}.json"


def _api_key_path(hashed: str) -> Path:
    return _api_keys_dir() / f"{hashed}.json"


def hash_password(password: str) -> str:
    # pbkdf2_hmac with sha256 + salt (avoid bcrypt dep for OSS)
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return base64.b64encode(salt + dk).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        raw = base64.b64decode(hashed.encode())
        salt = raw[:16]
        dk = raw[16:]
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
        return hmac_compare(check, dk)
    except:
        return False


def hmac_compare(a: bytes, b: bytes) -> bool:
    import hmac as _hmac

    return _hmac.compare_digest(a, b)


def list_users():
    out = []
    for f in _users_dir().glob("*.json"):
        try:
            with open(f) as jf:
                out.append(json.load(jf))
        except:
            continue
    return out


def get_user_by_id(uid: str) -> Optional[Dict[str, Any]]:
    p = _user_path(uid)
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except:
        return None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    email = email.lower().strip()
    for u in list_users():
        if u.get("email", "").lower() == email:
            return u
    return None


def create_user(
    email: str, password: str, role: str = "viewer", name: str = "", workspace_id: str = None
) -> Dict[str, Any]:
    email = email.lower().strip()
    if not email or "@" not in email:
        raise ValueError("Invalid email")
    if get_user_by_email(email):
        raise ValueError("Email already registered")
    if role not in ("admin", "editor", "viewer"):
        raise ValueError("role must be admin|editor|viewer")
    # first user is admin auto
    users = list_users()
    if not users:
        role = "admin"
    import uuid

    uid = str(uuid.uuid4())[:8]
    # workspace handling for cloud
    try:
        from app.config import get_workspace_id, is_cloud, get_base_storage_path

        if workspace_id is None and is_cloud():
            workspace_id = get_workspace_id()
    except:
        workspace_id = workspace_id or "default"
    if not workspace_id:
        workspace_id = "default"
    user = {
        "id": uid,
        "email": email,
        "password_hash": hash_password(password),
        "role": role,
        "name": name[:50],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workspace_id": workspace_id,
    }
    _atomic_write_json(_user_path(uid), user)
    return user


def update_user_role(uid: str, role: str) -> Optional[Dict[str, Any]]:
    u = get_user_by_id(uid)
    if not u:
        return None
    if role not in ("admin", "editor", "viewer"):
        raise ValueError("role must be admin|editor|viewer")
    u["role"] = role
    _atomic_write_json(_user_path(uid), u)
    return u


def seed_admin():
    # idempotent - called on startup. Never create predictable admin/admin.
    try:
        if list_users():
            return None
        email = os.getenv("ADMIN_EMAIL")
        pwd = os.getenv("ADMIN_PASSWORD")
        # Require explicit credentials; if not provided, generate secure one-time password
        if not email or not pwd:
            # No explicit creds — do not create admin/admin. Generate secure random.
            # For OSS dev convenience (AUTH_REQUIRED=false) we still need an admin but not predictable.
            # Generate and log; existing deployments with admin@local remain untouched (list_users check above).
            email = email or "admin@local"
            # generate secure password, log warning
            gen_pwd = secrets.token_urlsafe(16)
            try:
                import logging

                logging.getLogger(__name__).warning(
                    "ADMIN_PASSWORD not set — generated secure admin password for %s (store from logs, then set ADMIN_PASSWORD env for persistence).",
                    email,
                )
                # also print to stderr for visibility in docker logs
                print(
                    f"[SECURITY] Generated admin {email} password: {gen_pwd} — set ADMIN_EMAIL/ADMIN_PASSWORD env to persist",
                    flush=True,
                )
            except:
                pass
            pwd = gen_pwd
            # refuse to use predictable defaults
            if pwd in ("admin", "password", "123456"):
                pwd = secrets.token_urlsafe(16)
        else:
            # env provided but check not predictable fallback still
            if pwd == "admin" and email == "admin@local":
                # explicit admin/admin requested — allow only if explicitly set, but warn
                import logging

                logging.getLogger(__name__).warning(
                    "Using predictable admin/admin — set strong ADMIN_PASSWORD"
                )
        user = create_user(email, pwd, role="admin", name="Admin")
        return user
    except Exception as e:
        return None


def create_jwt(user: Dict[str, Any], exp_hours: int = 24) -> str:
    secret = _jwt_secret()
    ws_id = user.get("workspace_id") or "default"
    try:
        from jose import jwt

        exp = datetime.now(timezone.utc) + timedelta(hours=exp_hours)
        payload = {
            "sub": user["id"],
            "email": user.get("email"),
            "role": user.get("role", "viewer"),
            "ws_id": ws_id,
            "exp": int(exp.timestamp()),
        }
        return jwt.encode(payload, secret, algorithm=JWT_ALG)
    except ImportError:
        # Fallback: simple base64 without sig verification (for OSS without dep) — still works for tests
        import base64, json as _j

        header = (
            base64.urlsafe_b64encode(_j.dumps({"alg": "HS256", "typ": "JWT"}).encode())
            .decode()
            .rstrip("=")
        )
        payload = {
            "sub": user["id"],
            "email": user.get("email"),
            "role": user.get("role", "viewer"),
            "ws_id": ws_id,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=exp_hours)).timestamp()),
        }
        pay_b = base64.urlsafe_b64encode(_j.dumps(payload).encode()).decode().rstrip("=")
        sig = (
            base64.urlsafe_b64encode(hashlib.sha256(f"{header}.{pay_b}.{secret}".encode()).digest())
            .decode()
            .rstrip("=")
        )
        return f"{header}.{pay_b}.{sig}"


def decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    secret = _jwt_secret()
    try:
        from jose import jwt as _jwt, JWTError

        try:
            data = _jwt.decode(token, secret, algorithms=[JWT_ALG])
            return data
        except Exception:
            return None
    except ImportError:
        # Fallback verification for non-jose token
        try:
            import base64, json as _j

            parts = token.split(".")
            if len(parts) != 3:
                return None
            header_b, pay_b, sig = parts

            # pad
            def _pad(s):
                return s + "=" * (-len(s) % 4)

            payload_json = base64.urlsafe_b64decode(_pad(pay_b)).decode()
            data = _j.loads(payload_json)
            # check exp
            exp = data.get("exp")
            if exp and datetime.now(timezone.utc).timestamp() > exp:
                return None
            # verify sig
            header_b_check = header_b
            expected_sig = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(f"{header_b_check}.{pay_b}.{secret}".encode()).digest()
                )
                .decode()
                .rstrip("=")
            )
            import hmac as _hm

            if not _hm.compare_digest(expected_sig, sig):
                return None
            return data
        except:
            return None


def create_api_key(user_id: str, name: str = "", scopes: str = "read") -> Dict[str, Any]:
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("User not found")
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()[:24]
    # store
    ak = {
        "id": hashed[:8],
        "hashed": hashed,
        "user_id": user_id,
        "name": name[:50] or f"key_{hashed[:6]}",
        "scopes": scopes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(_api_key_path(hashed), ak)
    # Also store in user's keys list? Not needed, separate dir
    # Return raw once
    ak_with_raw = {**ak, "raw": raw, "api_key": raw}
    return ak_with_raw


def get_api_key_by_raw(raw: str) -> Optional[Dict[str, Any]]:
    hashed = hashlib.sha256(raw.encode()).hexdigest()[:24]
    p = _api_key_path(hashed)
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except:
        return None


def delete_api_key(hashed_or_id: str) -> bool:
    # Try id prefix
    found = None
    for f in _api_keys_dir().glob("*.json"):
        if f.stem.startswith(hashed_or_id) or f.stem == hashed_or_id:
            found = f
            break
        try:
            with open(f) as jf:
                data = json.load(jf)
                if data.get("id") == hashed_or_id or data.get("hashed") == hashed_or_id:
                    found = f
                    break
        except:
            continue
    if found:
        found.unlink()
        return True
    # Try raw hashed
    hashed = hashlib.sha256(hashed_or_id.encode()).hexdigest()[:24]
    p = _api_key_path(hashed)
    if p.exists():
        p.unlink()
        return True
    return False


def list_api_keys(user_id: str = None):
    out = []
    for f in _api_keys_dir().glob("*.json"):
        try:
            with open(f) as jf:
                data = json.load(jf)
                if user_id is None or data.get("user_id") == user_id:
                    out.append(data)
        except:
            continue
    return out


# L8 workspace helpers
def ensure_workspace(ws_id: str, name: str = "", owner_id: str = "") -> Path:
    from app.config import get_base_storage_path

    base = get_base_storage_path() / "workspaces" / ws_id
    base.mkdir(parents=True, exist_ok=True)
    for sub in ["datasets", "dashboards", "schedules", "reports", "conversations", "audit", "jobs"]:
        (base / sub).mkdir(parents=True, exist_ok=True)
    meta_p = base / "meta.json"
    if not meta_p.exists():
        import uuid as _uuid

        meta = {
            "id": ws_id,
            "name": name or ws_id,
            "owner_user_id": owner_id,
            "plan": "free",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write_json(meta_p, meta)
    else:
        try:
            with open(meta_p) as f:
                meta = json.load(f)
        except:
            meta = {}
    # billing.json
    b_p = base / "billing.json"
    if not b_p.exists():
        billing = {
            "workspace_id": ws_id,
            "plan": "free",
            "status": "active",
            "stripe_customer_id": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "queries_this_month": 0,
            "last_reset": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write_json(b_p, billing)
    return base


def get_workspace_meta(ws_id: str) -> Optional[Dict[str, Any]]:
    from app.config import get_base_storage_path

    p = get_base_storage_path() / "workspaces" / ws_id / "meta.json"
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except:
        return None


def list_workspaces() -> list:
    from app.config import get_base_storage_path

    base = get_base_storage_path() / "workspaces"
    if not base.exists():
        return []
    out = []
    for d in base.iterdir():
        if d.is_dir():
            m = get_workspace_meta(d.name)
            if m:
                out.append(m)
    return out
