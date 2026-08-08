from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import io
from app.services import scheduler_service

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class ScheduleCreate(BaseModel):
    name: Optional[str] = None
    dashboard_id: Optional[str] = None
    query: Optional[str] = None
    dataset_id: Optional[str] = None
    cron: str
    channel: str = "email"
    to: str
    threshold: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = True


@router.post("", status_code=201)
async def create_schedule(body: ScheduleCreate):
    try:
        sched = scheduler_service.create_schedule(body.model_dump())
        return sched
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_schedules():
    try:
        return scheduler_service.list_schedules()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sid}")
async def get_schedule(sid: str):
    s = scheduler_service.get_schedule(sid)
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return s


@router.delete("/{sid}")
async def delete_schedule(sid: str):
    ok = scheduler_service.delete_schedule(sid)
    if not ok:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted", "id": sid}


@router.post("/{sid}/run")
async def run_schedule_now(sid: str):
    s = scheduler_service.get_schedule(sid)
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    try:
        res = scheduler_service.run_schedule_now(sid)
        return res
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sid}/runs")
async def get_runs(sid: str):
    s = scheduler_service.get_schedule(sid)
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {
        "id": sid,
        "runs": s.get("runs", []),
        "last_run": s.get("last_run"),
        "next_run": s.get("next_run"),
    }


@router.get("/{sid}/export")
async def export_schedule_pdf(sid: str):
    # Manual export of last run PDF (regenerate)
    s = scheduler_service.get_schedule(sid)
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    # Generate fresh PDF without sending
    try:
        from app.services.dashboard_service import get_dashboard
        from app.core.exporter import dashboard_to_pdf

        dash_id = s.get("dashboard_id")
        if not dash_id:
            raise HTTPException(
                status_code=400, detail="Schedule has no dashboard_id — cannot export PDF"
            )
        dash = get_dashboard(dash_id)
        if not dash:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        pdf = dashboard_to_pdf(dash)
        headers = {"Content-Disposition": f'attachment; filename="schedule_{sid}.pdf"'}
        return StreamingResponse(pdf, media_type="application/pdf", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
