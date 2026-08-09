import uuid
import secrets
from typing import Dict, Any, List, Optional
from datetime import timezone, datetime
from pathlib import Path
import json

from app.core import storage
from app.core.storage import _atomic_write_json
from app.config import get_storage_path


def _dashboards_dir() -> Path:
    d = get_storage_path() / "dashboards"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dashboard_path(dash_id: str) -> Path:
    return _dashboards_dir() / f"{dash_id}.json"


def generate_slug() -> str:
    # 8-char urlsafe, collision check
    for _ in range(10):
        slug = secrets.token_urlsafe(6)[:8]  # ~8 chars
        # Ensure no existing dashboard has this slug
        existing = [f for f in _dashboards_dir().glob("*.json")]
        slugs = set()
        for f in existing:
            try:
                with open(f) as jf:
                    data = json.load(jf)
                    if data.get("share_slug"):
                        slugs.add(data["share_slug"])
            except:
                continue
        if slug not in slugs:
            return slug
    return secrets.token_urlsafe(8)[:8]


def create_dashboard(dataset_id: str, name: str, description: str = "") -> Dict[str, Any]:
    # Validate dataset exists
    meta = storage.get_dataset_meta(dataset_id)
    if not meta:
        raise FileNotFoundError(f"Dataset {dataset_id} not found")
    dash_id = str(uuid.uuid4())[:8]
    dash = {
        "id": dash_id,
        "dataset_id": dataset_id,
        "name": name[:100] if name else f"Dashboard {dash_id}",
        "description": description[:500] if description else "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "is_public": False,
        "share_slug": None,
        "widgets": [],
    }
    _atomic_write_json(_dashboard_path(dash_id), dash)
    return dash


def get_dashboard(dash_id: str) -> Optional[Dict[str, Any]]:
    p = _dashboard_path(dash_id)
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def list_dashboards(dataset_id: Optional[str] = None) -> List[Dict[str, Any]]:
    dashboards = []
    for f in _dashboards_dir().glob("*.json"):
        try:
            with open(f) as jf:
                data = json.load(jf)
                if dataset_id is None or data.get("dataset_id") == dataset_id:
                    dashboards.append(data)
        except:
            continue
    dashboards.sort(key=lambda x: x.get("updated_at", x.get("created_at", "")), reverse=True)
    return dashboards


def delete_dashboard(dash_id: str) -> bool:
    p = _dashboard_path(dash_id)
    if p.exists():
        p.unlink()
        return True
    return False


def add_widget(dash_id: str, widget_data: Dict[str, Any]) -> Dict[str, Any]:
    dash = get_dashboard(dash_id)
    if not dash:
        raise FileNotFoundError(f"Dashboard {dash_id} not found")
    # widget_data should have query, code, result, chart, title
    widget_id = str(uuid.uuid4())[:6]
    # Get current dataset version for staleness
    meta = storage.get_dataset_meta(dash["dataset_id"])
    dataset_version = meta.get("current_version", 0) if meta else 0
    widget = {
        "id": widget_id,
        "query": widget_data.get("query", "")[:500],
        "code": widget_data.get("code", "")[:5000],
        "result": widget_data.get("result"),
        "chart": widget_data.get("chart"),
        "title": widget_data.get("title", widget_data.get("query", "")[:60])[:100],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset_version,
    }
    dash["widgets"].append(widget)
    dash["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(_dashboard_path(dash_id), dash)
    return widget


def remove_widget(dash_id: str, widget_id: str) -> bool:
    dash = get_dashboard(dash_id)
    if not dash:
        return False
    before = len(dash["widgets"])
    dash["widgets"] = [w for w in dash["widgets"] if w["id"] != widget_id]
    if len(dash["widgets"]) == before:
        return False
    dash["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(_dashboard_path(dash_id), dash)
    return True


def refresh_widget(dash_id: str, widget_id: str) -> Optional[Dict[str, Any]]:
    dash = get_dashboard(dash_id)
    if not dash:
        raise FileNotFoundError(f"Dashboard {dash_id} not found")
    widget = next((w for w in dash["widgets"] if w["id"] == widget_id), None)
    if not widget:
        raise FileNotFoundError(f"Widget {widget_id} not found")
    code = widget.get("code", "")
    if not code:
        raise ValueError("Widget has no code to refresh")
    # Validate and execute
    from app.core.security import validate_code
    from app.agent.executor import execute_code
    from app.core.storage import load_dataset_df

    validate_code(code)
    df = load_dataset_df(dash["dataset_id"])
    exec_res = execute_code(code, df)
    if not exec_res["success"]:
        raise RuntimeError(f"Refresh failed: {exec_res['error']}")
    # Update widget
    widget["result"] = exec_res.get("result_json")
    widget["chart"] = exec_res.get("chart_json")
    # Update version
    meta = storage.get_dataset_meta(dash["dataset_id"])
    widget["dataset_version"] = meta.get("current_version", 0) if meta else 0
    widget["updated_at"] = datetime.now(timezone.utc).isoformat()
    dash["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(_dashboard_path(dash_id), dash)
    return widget


def share_dashboard(dash_id: str) -> Dict[str, Any]:
    dash = get_dashboard(dash_id)
    if not dash:
        raise FileNotFoundError(f"Dashboard {dash_id} not found")
    if dash.get("is_public") and dash.get("share_slug"):
        return {
            "slug": dash["share_slug"],
            "is_public": True,
            "url": f"/api/dashboards/share/{dash['share_slug']}",
        }
    slug = generate_slug()
    dash["is_public"] = True
    dash["share_slug"] = slug
    dash["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(_dashboard_path(dash_id), dash)
    return {"slug": slug, "is_public": True, "url": f"/api/dashboards/share/{slug}"}


def unshare_dashboard(dash_id: str) -> Dict[str, Any]:
    dash = get_dashboard(dash_id)
    if not dash:
        raise FileNotFoundError(f"Dashboard {dash_id} not found")
    dash["is_public"] = False
    # Keep slug for potential re-share, but could clear
    dash["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(_dashboard_path(dash_id), dash)
    return {"is_public": False, "slug": dash.get("share_slug")}


def get_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    for f in _dashboards_dir().glob("*.json"):
        try:
            with open(f) as jf:
                data = json.load(jf)
                if data.get("share_slug") == slug and data.get("is_public"):
                    return data
        except:
            continue
    return None


def export_dashboard_csv(dash_id: str) -> Dict[str, Any]:
    dash = get_dashboard(dash_id)
    if not dash:
        raise FileNotFoundError(f"Dashboard {dash_id} not found")
    # For now, return dashboard JSON; frontend will create zip via multiple CSVs
    # We can also generate a zip in backend, but for L3 we return dashboard and let frontend handle CSV per widget
    return dash
