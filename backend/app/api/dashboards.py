import os
import json
import zipfile
import io
import csv
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import pandas as pd

from app.core import storage
from app.services import dashboard_service
from app.core.audit import log as audit_log
from app.api.auth import get_current_user, require_role
from fastapi import Depends, Request

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


class CreateDashboardRequest(BaseModel):
    dataset_id: str
    name: str
    description: Optional[str] = ""


class AddWidgetRequest(BaseModel):
    query: str
    code: Optional[str] = ""
    result: Optional[Dict[str, Any]] = None
    chart: Optional[Dict[str, Any]] = None
    title: Optional[str] = ""


@router.post("", status_code=201)
async def create_dashboard(
    body: CreateDashboardRequest, request: Request = None, user=Depends(get_current_user)
):
    if user.get("role") not in ("admin", "editor"):
        raise HTTPException(status_code=403, detail="Viewer cannot create dashboards")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Dashboard name cannot be empty")
    if len(body.name) > 100:
        raise HTTPException(status_code=400, detail="Dashboard name too long (max 100)")
    try:
        dash = dashboard_service.create_dashboard(
            body.dataset_id, body.name.strip(), body.description or ""
        )
        audit_log(
            "dashboard.create",
            user,
            dashboard_id=dash["id"],
            dataset_id=body.dataset_id,
            ip=request.client.host if request and request.client else "",
        )
        return dash
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_dashboards(
    dataset_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    try:
        dashboards = dashboard_service.list_dashboards(dataset_id)
        return dashboards[offset : offset + limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/share/{slug}")
async def get_shared_dashboard(slug: str):
    dash = dashboard_service.get_by_slug(slug)
    if not dash:
        raise HTTPException(status_code=404, detail="Shared dashboard not found or not public")
    return dash


@router.get("/{dash_id}")
async def get_dashboard(dash_id: str):
    dash = dashboard_service.get_dashboard(dash_id)
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dash


@router.delete("/{dash_id}")
async def delete_dashboard(dash_id: str, request: Request = None, user=Depends(get_current_user)):
    if user.get("role") not in ("admin", "editor"):
        raise HTTPException(status_code=403, detail="Viewer cannot delete dashboards")
    ok = dashboard_service.delete_dashboard(dash_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    audit_log(
        "dashboard.delete",
        user,
        dashboard_id=dash_id,
        ip=request.client.host if request and request.client else "",
    )
    return {"status": "deleted", "id": dash_id}


@router.post("/{dash_id}/widgets")
async def add_widget(
    dash_id: str, body: AddWidgetRequest, request: Request = None, user=Depends(get_current_user)
):
    if user.get("role") not in ("admin", "editor"):
        raise HTTPException(status_code=403, detail="Viewer cannot add widgets")
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        widget = dashboard_service.add_widget(dash_id, body.model_dump())
        audit_log(
            "dashboard.add_widget",
            user,
            dashboard_id=dash_id,
            ip=request.client.host if request and request.client else "",
        )
        return widget
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{dash_id}/widgets/{widget_id}")
async def remove_widget(
    dash_id: str, widget_id: str, request: Request = None, user=Depends(get_current_user)
):
    if user.get("role") not in ("admin", "editor"):
        raise HTTPException(status_code=403, detail="Viewer cannot remove widgets")
    dash = dashboard_service.get_dashboard(dash_id)
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    ok = dashboard_service.remove_widget(dash_id, widget_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Widget not found")
    audit_log(
        "dashboard.remove_widget",
        user,
        dashboard_id=dash_id,
        ip=request.client.host if request and request.client else "",
    )
    return {"status": "removed", "widget_id": widget_id}


@router.post("/{dash_id}/widgets/{widget_id}/refresh")
async def refresh_widget(dash_id: str, widget_id: str):
    try:
        widget = dashboard_service.refresh_widget(dash_id, widget_id)
        return widget
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{dash_id}/share")
async def share_dashboard(dash_id: str):
    try:
        res = dashboard_service.share_dashboard(dash_id)
        return res
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{dash_id}/unshare")
async def unshare_dashboard(dash_id: str):
    try:
        res = dashboard_service.unshare_dashboard(dash_id)
        return res
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{dash_id}/duplicate")
async def duplicate_dashboard(dash_id: str):
    dash = dashboard_service.get_dashboard(dash_id)
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    try:
        new_dash = dashboard_service.create_dashboard(
            dash["dataset_id"], f"{dash['name']} (copy)", dash.get("description", "")
        )
        # Copy widgets
        for w in dash.get("widgets", []):
            dashboard_service.add_widget(
                new_dash["id"],
                {
                    "query": w.get("query", ""),
                    "code": w.get("code", ""),
                    "result": w.get("result"),
                    "chart": w.get("chart"),
                    "title": w.get("title", ""),
                },
            )
        return dashboard_service.get_dashboard(new_dash["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dash_id}/export")
async def export_dashboard(dash_id: str, format: str = Query("json", pattern="^(json|csv|pdf)$")):
    dash = dashboard_service.get_dashboard(dash_id)
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if format == "json":
        # Return dashboard json
        return JSONResponse(
            content=dash, headers={"Content-Disposition": f'attachment; filename="{dash_id}.json"'}
        )
    elif format == "csv":
        # Zip of CSVs per widget result + dashboard.json
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            # Add dashboard.json
            z.writestr("dashboard.json", json.dumps(dash, indent=2))
            for idx, w in enumerate(dash.get("widgets", [])):
                result = w.get("result")
                title = w.get("title", f"widget_{idx}") or f"widget_{idx}"
                safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:40]
                if result and result.get("columns") and result.get("data") is not None:
                    # Create CSV
                    try:
                        df = pd.DataFrame(result["data"], columns=result["columns"])
                        csv_buf = io.StringIO()
                        df.to_csv(csv_buf, index=False)
                        z.writestr(f"{idx+1}_{safe_title}.csv", csv_buf.getvalue())
                    except Exception:
                        # Fallback raw result
                        z.writestr(f"{idx+1}_{safe_title}.json", json.dumps(result, indent=2))
                elif result:
                    z.writestr(f"{idx+1}_{safe_title}.json", json.dumps(result, indent=2))
                # Chart also as json
                if w.get("chart"):
                    z.writestr(f"{idx+1}_{safe_title}_chart.json", json.dumps(w["chart"], indent=2))
        buf.seek(0)
        headers = {"Content-Disposition": f'attachment; filename="{dash_id}_export.zip"'}
        return StreamingResponse(buf, media_type="application/zip", headers=headers)
    elif format == "pdf":
        from app.core.exporter import dashboard_to_pdf

        share_url = None
        if dash.get("share_slug") and dash.get("is_public"):
            share_url = f"/api/dashboards/share/{dash['share_slug']}"
        pdf = dashboard_to_pdf(dash, share_url=share_url)
        headers = {"Content-Disposition": f'attachment; filename="{dash_id}.pdf"'}
        return StreamingResponse(pdf, media_type="application/pdf", headers=headers)


# Comments
class CommentCreate(BaseModel):
    text: str
    user: Optional[str] = "anon"
    parent_id: Optional[str] = None


@router.post("/{dash_id}/comments", status_code=201)
async def add_comment(
    dash_id: str, body: CommentCreate, request: Request = None, user=Depends(get_current_user)
):
    # Viewer can comment? Allow editor/admin/viewer but not anon when AUTH_REQUIRED
    if user.get("id") == "anon" and os.getenv("AUTH_REQUIRED", "false").lower() in (
        "true",
        "1",
        "yes",
    ):
        raise HTTPException(status_code=401, detail="Authentication required")
    dash = dashboard_service.get_dashboard(dash_id)
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Comment text cannot be empty")
    if len(body.text) > 1000:
        raise HTTPException(status_code=400, detail="Comment too long (max 1000)")
    import uuid, datetime

    comment = {
        "id": str(uuid.uuid4())[:8],
        "user": user.get("email") if user.get("id") != "anon" else (body.user or "anon")[:50],
        "text": body.text.strip()[:1000],
        "parent_id": body.parent_id,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    comments = dash.get("comments", [])
    if len(comments) >= 100:
        raise HTTPException(status_code=400, detail="Too many comments (max 100)")
    comments.append(comment)
    dash["comments"] = comments
    dash["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # Persist
    from pathlib import Path
    from app.config import get_storage_path
    from app.core.storage import _atomic_write_json

    path = get_storage_path() / "dashboards" / f"{dash_id}.json"
    _atomic_write_json(path, dash)
    audit_log(
        "dashboard.comment",
        user,
        dashboard_id=dash_id,
        ip=request.client.host if request and request.client else "",
        extra=comment["text"][:100],
    )
    return comment


@router.get("/{dash_id}/comments")
async def list_comments(dash_id: str):
    dash = dashboard_service.get_dashboard(dash_id)
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dash.get("comments", [])


@router.delete("/{dash_id}/comments/{cid}")
async def delete_comment(dash_id: str, cid: str):
    dash = dashboard_service.get_dashboard(dash_id)
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    comments = dash.get("comments", [])
    before = len(comments)
    comments = [c for c in comments if c["id"] != cid]
    if len(comments) == before:
        raise HTTPException(status_code=404, detail="Comment not found")
    dash["comments"] = comments
    import datetime

    dash["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    from app.config import get_storage_path
    from app.core.storage import _atomic_write_json

    path = get_storage_path() / "dashboards" / f"{dash_id}.json"
    _atomic_write_json(path, dash)
    return {"status": "deleted", "id": cid}
