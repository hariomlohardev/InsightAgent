import uuid
import json
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.config import get_storage_path
from app.core.storage import _atomic_write_json

router = APIRouter(prefix="/api/reports", tags=["reports"])

def _reports_dir() -> Path:
    d = get_storage_path() / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _report_path(rid: str) -> Path:
    return _reports_dir() / f"{rid}.json"

class Block(BaseModel):
    type: str  # widget | markdown
    widget_id: Optional[str] = None
    text: Optional[str] = None

class ReportCreate(BaseModel):
    dashboard_id: str
    name: str
    description: Optional[str] = ""
    blocks: List[Dict[str, Any]]

@router.post("", status_code=201)
async def create_report(body: ReportCreate):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Report name required")
    if len(body.name) > 120:
        raise HTTPException(status_code=400, detail="Name too long")
    # Validate dashboard exists
    from app.services.dashboard_service import get_dashboard
    dash = get_dashboard(body.dashboard_id)
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    # Validate blocks
    for b in body.blocks:
        if b.get("type") not in ("widget","markdown"):
            raise HTTPException(status_code=400, detail="Block type must be widget|markdown")
        if b.get("type") == "widget" and not b.get("widget_id"):
            raise HTTPException(status_code=400, detail="widget_id required for widget block")
        if b.get("type") == "markdown" and not b.get("text"):
            raise HTTPException(status_code=400, detail="text required for markdown block")
    # Widget ids must exist in dashboard
    widget_ids = {w["id"] for w in dash.get("widgets",[])}
    for b in body.blocks:
        if b.get("type")=="widget" and b.get("widget_id") not in widget_ids:
            raise HTTPException(status_code=400, detail=f"Widget {b['widget_id']} not in dashboard")
    rid = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()
    report = {
        "id": rid,
        "dashboard_id": body.dashboard_id,
        "name": body.name.strip(),
        "description": body.description or "",
        "blocks": body.blocks,
        "created_at": now,
        "updated_at": now,
    }
    _atomic_write_json(_report_path(rid), report)
    return report

@router.get("")
async def list_reports(dashboard_id: Optional[str] = None):
    out = []
    for f in _reports_dir().glob("*.json"):
        try:
            import json as _j
            with open(f) as jf:
                data = _j.load(jf)
                if dashboard_id is None or data.get("dashboard_id")==dashboard_id:
                    out.append(data)
        except:
            continue
    out.sort(key=lambda x: x.get("created_at",""), reverse=True)
    return out

@router.get("/{rid}")
async def get_report(rid: str):
    p = _report_path(rid)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    try:
        import json as _j
        with open(p) as f:
            return _j.load(f)
    except:
        raise HTTPException(status_code=500, detail="Failed to load report")

@router.delete("/{rid}")
async def delete_report(rid: str):
    p = _report_path(rid)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    p.unlink()
    return {"status": "deleted", "id": rid}

@router.get("/{rid}/export")
async def export_report(rid: str, format: str = "pdf"):
    p = _report_path(rid)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    import json as _j
    with open(p) as f:
        report = _j.load(f)
    if format not in ("pdf","json","csv"):
        raise HTTPException(status_code=400, detail="format must be pdf|json|csv")
    if format == "json":
        from fastapi.responses import JSONResponse
        return JSONResponse(content=report)
    if format == "csv":
        # Zip of widget CSVs
        from app.services.dashboard_service import get_dashboard
        dash = get_dashboard(report["dashboard_id"])
        if not dash:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        import io, zipfile, json as _js, pandas as pd
        buf = io.BytesIO()
        with zipfile.ZipFile(buf,"w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("report.json", _j.dumps(report, indent=2))
            widget_map = {w["id"]: w for w in dash.get("widgets",[])}
            for b in report.get("blocks",[]):
                if b.get("type")=="widget":
                    w = widget_map.get(b.get("widget_id"))
                    if w and w.get("result"):
                        res = w["result"]
                        if res.get("columns") and res.get("data"):
                            try:
                                df = pd.DataFrame(res["data"], columns=res["columns"]) if isinstance(res["data"][0], list) else pd.DataFrame(res["data"])
                            except:
                                try:
                                    df = pd.DataFrame(res["data"])
                                except:
                                    continue
                            csv_buf = io.StringIO()
                            df.to_csv(csv_buf, index=False)
                            z.writestr(f"{w.get('title','widget')[:30]}.csv", csv_buf.getvalue())
        buf.seek(0)
        headers = {"Content-Disposition": f"attachment; filename=\"report_{rid}.zip\""}
        return StreamingResponse(buf, media_type="application/zip", headers=headers)
    # pdf
    from app.services.dashboard_service import get_dashboard
    from app.core.exporter import report_to_pdf
    dash = get_dashboard(report["dashboard_id"])
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    share_url = None
    if dash.get("share_slug") and dash.get("is_public"):
        share_url = f"/api/dashboards/share/{dash['share_slug']}"
    pdf = report_to_pdf(report, dashboard=dash, share_url=share_url)
    headers = {"Content-Disposition": f"attachment; filename=\"report_{rid}.pdf\""}
    return StreamingResponse(pdf, media_type="application/pdf", headers=headers)
