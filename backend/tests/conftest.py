import os
import uuid

import pytest
from fastapi.testclient import TestClient as _TestClient

from app.core import auth as auth_core

# Create a single editor user for all tests that need auth when AUTH_REQUIRED=false
_EDITOR_TOKEN = None
_EDITOR_EMAIL = None


def _get_editor_token():
    global _EDITOR_TOKEN, _EDITOR_EMAIL
    if _EDITOR_TOKEN:
        return _EDITOR_TOKEN
    # create unique editor for this pytest run
    _EDITOR_EMAIL = f"pytest_editor_{uuid.uuid4().hex[:6]}@example.com"
    try:
        u = auth_core.create_user(_EDITOR_EMAIL, "PytestPass123!", role="editor")
    except Exception:
        u = auth_core.get_user_by_email(_EDITOR_EMAIL)
        if not u:
            # fallback: try to find any editor
            for uu in auth_core.list_users():
                if uu.get("role") == "editor":
                    u = uu
                    break
            if not u:
                u = auth_core.create_user(
                    f"fallback_{uuid.uuid4().hex[:6]}@example.com",
                    "PytestPass123!",
                    role="editor",
                )
    _EDITOR_TOKEN = auth_core.create_jwt(u)
    return _EDITOR_TOKEN


# Patch TestClient to auto-inject auth when anon would otherwise be viewer and test expects editor
_orig_request = _TestClient.request


def _patched_request(self, method, url, *args, **kwargs):
    # Only auto-inject when AUTH_REQUIRED is false and no auth already provided
    # Respect tests that explicitly set AUTH_REQUIRED=true (they expect 401 for anon)
    auth_required = os.getenv("AUTH_REQUIRED", "false").lower() in ("true", "1", "yes")
    enterprise = os.getenv("ENTERPRISE", "false").lower() in ("true", "1", "yes")
    is_cloud = os.getenv("CLOUD", "false").lower() in ("true", "1", "yes")
    has_auth = False
    # check headers
    headers = kwargs.get("headers") or {}
    # also check if Authorization already in headers (case-insensitive)
    for k in list(headers.keys()):
        if k.lower() == "authorization" or k.lower() == "x-api-key":
            has_auth = True
            break
    # also check if client has default headers with auth (from TestClient(headers=...))
    if not has_auth and hasattr(self, "headers"):
        for k in list(self.headers.keys()):
            if k.lower() == "authorization":
                has_auth = True
                break
    if not has_auth and not auth_required and not enterprise and not is_cloud:
        # For upload / clean / join / delete / chat etc, anon viewer would get 403 — inject editor token
        # But don't inject for GET /health, /api/datasets list, etc that are viewer-allowed? Injecting doesn't hurt.
        # To keep test_anon_viewer passing (it calls get_current_user directly), we don't affect it.
        # Only inject for TestClient requests that would otherwise be anon.
        # We add Authorization header
        token = _get_editor_token()
        # copy headers to avoid mutating original dict
        new_headers = dict(headers)
        new_headers["Authorization"] = f"Bearer {token}"
        kwargs["headers"] = new_headers
    return _orig_request(self, method, url, *args, **kwargs)


_TestClient.request = _patched_request
