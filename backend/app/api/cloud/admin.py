from fastapi import APIRouter, Depends, HTTPException
from app.api.auth import get_current_user, require_role
from app.config import get_base_storage_path
from app.core.billing import get_billing, get_usage

router = APIRouter(prefix="/api/cloud/admin", tags=["cloud-admin"])


@router.get("/stats")
async def admin_stats(user=Depends(require_role("admin"))):
    # only when CLOUD? Allow always but cloud stats more
    import os, json
    from app.core.auth import list_workspaces
    from app.core.storage import list_datasets as _list_ds

    ws = list_workspaces()
    total_ws = len(ws)
    # MRR calculation: sum per plan price
    price_map = {"free": 0, "pro": 19, "team": 49, "enterprise": 499}
    mrr = 0
    active_subs = 0
    total_datasets = 0
    for w in ws:
        plan = w.get("plan", "free")
        if plan != "free":
            active_subs += 1
        mrr += price_map.get(plan, 0)
    # Count total datasets across workspaces (base storage datasets + workspaces)
    base = get_base_storage_path()
    # datasets in default storage (when not cloud) + workspaces
    try:
        # default
        from pathlib import Path

        default_ds = base / "datasets"
        if default_ds.exists():
            total_datasets += sum(1 for _ in default_ds.iterdir() if _.is_dir())
        ws_base = base / "workspaces"
        if ws_base.exists():
            for w in ws_base.iterdir():
                ddir = w / "datasets"
                if ddir.exists():
                    total_datasets += sum(1 for _ in ddir.iterdir() if _.is_dir())
    except:
        pass
    # also schedules count
    total_schedules = 0
    try:
        from app.config import get_base_storage_path as _gbs

        wb = _gbs() / "workspaces"
        if wb.exists():
            for w in wb.iterdir():
                sdir = w / "schedules"
                if sdir.exists():
                    total_schedules += sum(1 for _ in sdir.glob("*.json"))
        # default schedules
        if (base / "schedules").exists():
            total_schedules += sum(1 for _ in (base / "schedules").glob("*.json"))
    except:
        pass
    return {
        "total_workspaces": total_ws,
        "mrr": mrr,
        "active_subscriptions": active_subs,
        "total_datasets": total_datasets,
        "active_schedules": total_schedules,
    }
