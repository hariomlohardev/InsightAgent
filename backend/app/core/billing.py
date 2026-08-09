import json, os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from app.config import get_storage_path, get_base_storage_path, get_workspace_id, is_cloud
from app.core.storage import _atomic_write_json

# Quotas per plan (from 00_ROADMAP)
PLAN_QUOTAS = {
    "free": {"datasets": 3, "queries_per_month": 50, "users": 1, "schedules": 2},
    "pro": {"datasets": 100, "queries_per_month": 10000, "users": 5, "schedules": 50},
    "team": {"datasets": 500, "queries_per_month": 100000, "users": 20, "schedules": 200},
    "enterprise": {
        "datasets": 10000,
        "queries_per_month": 1000000,
        "users": 1000,
        "schedules": 1000,
    },
}


def _billing_path(ws_id: str = None) -> Path:
    if ws_id is None:
        ws_id = get_workspace_id()
    base = get_base_storage_path() / "workspaces" / ws_id
    base.mkdir(parents=True, exist_ok=True)
    return base / "billing.json"


def get_billing(ws_id: str = None) -> Dict[str, Any]:
    p = _billing_path(ws_id)
    if not p.exists():
        # create free
        billing = {
            "workspace_id": ws_id or get_workspace_id(),
            "plan": "free",
            "status": "active",
            "stripe_customer_id": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "queries_this_month": 0,
            "last_reset": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_write_json(p, billing)
        return billing
    try:
        with open(p) as f:
            data = json.load(f)
        # check monthly reset
        try:
            last = datetime.fromisoformat(
                data.get(
                    "last_reset", data.get("created_at", datetime.now(timezone.utc).isoformat())
                ).replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            if now.month != last.month or now.year != last.year:
                data["queries_this_month"] = 0
                data["last_reset"] = now.isoformat()
                _atomic_write_json(p, data)
        except Exception:
            pass
        return data
    except Exception:
        return {"plan": "free", "queries_this_month": 0}


def set_plan(ws_id: str, plan: str, stripe_customer_id: str = None, status: str = "active"):
    p = _billing_path(ws_id)
    billing = get_billing(ws_id)
    billing["plan"] = plan
    billing["status"] = status
    if stripe_customer_id:
        billing["stripe_customer_id"] = stripe_customer_id
    billing["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(p, billing)
    # also update workspace meta plan
    try:
        meta_p = get_base_storage_path() / "workspaces" / ws_id / "meta.json"
        if meta_p.exists():
            with open(meta_p) as f:
                meta = json.load(f)
            meta["plan"] = plan
            _atomic_write_json(meta_p, meta)
    except Exception:
        pass
    return billing


def get_plan(ws_id: str = None) -> str:
    return get_billing(ws_id).get("plan", "free")


def get_usage(ws_id: str = None) -> Dict[str, Any]:
    billing = get_billing(ws_id)
    ws = ws_id or get_workspace_id()
    # count datasets
    from app.config import get_base_storage_path

    base = get_base_storage_path() / "workspaces" / ws
    if not base.exists() or not is_cloud():
        # fallback to current storage path
        from app.core.storage import list_datasets

        datasets = len(list_datasets())
    else:
        # count meta.json in datasets
        ddir = base / "datasets"
        cnt = 0
        if ddir.exists():
            cnt = sum(1 for _ in ddir.iterdir() if _.is_dir())
        datasets = cnt
    queries = billing.get("queries_this_month", 0)
    return {
        "datasets": datasets,
        "queries_this_month": queries,
        "plan": billing.get("plan", "free"),
        "status": billing.get("status", "active"),
    }


def can_create_dataset(ws_id: str = None) -> tuple[bool, str]:
    if not is_cloud():
        return True, ""
    plan = get_plan(ws_id)
    quotas = PLAN_QUOTAS.get(plan, PLAN_QUOTAS["free"])
    usage = get_usage(ws_id)
    if usage["datasets"] >= quotas["datasets"]:
        return False, f"Free limit {quotas['datasets']} datasets, upgrade at /pricing (plan={plan})"
    return True, ""


def can_query(ws_id: str = None) -> tuple[bool, str]:
    if not is_cloud():
        return True, ""
    plan = get_plan(ws_id)
    quotas = PLAN_QUOTAS.get(plan, PLAN_QUOTAS["free"])
    billing = get_billing(ws_id)
    if billing.get("queries_this_month", 0) >= quotas["queries_per_month"]:
        return (
            False,
            f"Monthly query limit {quotas['queries_per_month']} reached for plan {plan}, upgrade at /pricing",
        )
    return True, ""


def increment_query(ws_id: str = None):
    if not is_cloud():
        return
    p = _billing_path(ws_id)
    billing = get_billing(ws_id)
    billing["queries_this_month"] = billing.get("queries_this_month", 0) + 1
    _atomic_write_json(p, billing)
