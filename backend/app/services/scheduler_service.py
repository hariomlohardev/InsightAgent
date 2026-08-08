import uuid
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import get_storage_path
from app.core.storage import _atomic_write_json


def _schedules_dir() -> Path:
    d = get_storage_path() / "schedules"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _schedule_path(sid: str) -> Path:
    return _schedules_dir() / f"{sid}.json"


def _validate_cron(cron: str):
    if not cron or not isinstance(cron, str):
        raise ValueError("cron required (e.g., '0 9 * * 1' for Mondays 9am)")
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError("cron must have 5 fields: 'm h dom mon dow' e.g., '0 9 * * *'")
    # lightweight validation via croniter if available else rely on APScheduler
    try:
        from apscheduler.triggers.cron import CronTrigger

        CronTrigger.from_crontab(cron)
    except Exception as e:
        raise ValueError(f"Invalid cron '{cron}': {e}")


def list_schedules() -> List[Dict[str, Any]]:
    out = []
    for f in _schedules_dir().glob("*.json"):
        try:
            with open(f) as jf:
                data = json.load(jf)
                out.append(data)
        except:
            continue
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out


def get_schedule(sid: str) -> Optional[Dict[str, Any]]:
    p = _schedule_path(sid)
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except:
        return None


def create_schedule(data: Dict[str, Any]) -> Dict[str, Any]:
    # data: {dashboard_id?, query?, dataset_id, cron, channel, to, threshold?, name}
    cron = data.get("cron", "").strip()
    _validate_cron(cron)
    channel = (data.get("channel") or "email").lower()
    # Fix duplicate check earlier? channel must be email|slack
    if channel not in ("email", "slack", "both"):
        raise ValueError("channel must be email|slack|both")
    to_addr = data.get("to") or data.get("recipient") or ""
    if not to_addr.strip():
        # Channel-specific default: for slack, webhook url may be in env, but we require at least placeholder
        # Allow empty for testing? No, require for email/slack
        raise ValueError("to required (email address or slack webhook url)")
    dataset_id = data.get("dataset_id")
    dashboard_id = data.get("dashboard_id")
    query = data.get("query")
    # At least one of dashboard_id or query or dataset_id+query
    if not dashboard_id and not query:
        # try query from data
        if not dataset_id:
            raise ValueError("Provide dashboard_id or query (and dataset_id if query)")
    name = data.get("name") or f"Schedule {dashboard_id or query[:20]}"
    threshold = data.get("threshold")  # optional: {"pct": 10, "direction": "drop"}
    sid = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()
    sched = {
        "id": sid,
        "name": name[:120],
        "dashboard_id": dashboard_id,
        "query": query,
        "dataset_id": dataset_id,
        "cron": cron,
        "channel": channel,
        "to": to_addr.strip()[:300],
        "threshold": threshold,
        "created_at": now,
        "updated_at": now,
        "enabled": True,
        "last_run": None,
        "next_run": None,
        "runs": [],  # last 5
    }
    _atomic_write_json(_schedule_path(sid), sched)
    # Try to add to APScheduler
    try:
        from app.services.scheduler import add_job

        add_job(sched)
    except Exception as e:
        # If scheduler not running yet (tests), just persist
        pass
    return sched


def delete_schedule(sid: str) -> bool:
    # Remove from APScheduler
    try:
        from app.services.scheduler import remove_job

        remove_job(sid)
    except:
        pass
    p = _schedule_path(sid)
    if p.exists():
        p.unlink()
        return True
    return False


def _record_run(sid: str, status: str, detail: str = "", pdf_bytes_len: int = 0):
    sched = get_schedule(sid)
    if not sched:
        return
    now = datetime.utcnow().isoformat()
    run = {"at": now, "status": status, "detail": detail[:500], "pdf_bytes": pdf_bytes_len}
    runs = sched.get("runs", [])
    runs.insert(0, run)
    runs = runs[:5]
    sched["runs"] = runs
    sched["last_run"] = now
    sched["updated_at"] = now
    _atomic_write_json(_schedule_path(sid), sched)


def run_schedule(sid: str) -> Dict[str, Any]:
    sched = get_schedule(sid)
    if not sched:
        raise FileNotFoundError(f"Schedule {sid} not found")
    if not sched.get("enabled", True):
        _record_run(sid, "skipped", "disabled")
        return {"status": "skipped", "reason": "disabled"}

    dashboard_id = sched.get("dashboard_id")
    query = sched.get("query")
    dataset_id = sched.get("dataset_id")
    channel = sched.get("channel", "email")
    to_addr = sched.get("to")

    try:
        pdf_buf = None
        share_url = None
        text_summary = ""
        # Path 1: dashboard
        if dashboard_id:
            from app.services.dashboard_service import get_dashboard
            from app.core import storage
            from app.core.exporter import dashboard_to_pdf

            dash = get_dashboard(dashboard_id)
            if not dash:
                raise ValueError(f"Dashboard {dashboard_id} not found")
            # Re-execute each widget's code on current data for fresh results
            fresh_results = []
            for w in dash.get("widgets", []):
                code = w.get("code")
                if code:
                    try:
                        from app.core.security import validate_code
                        from app.agent.executor import execute_code
                        from app.core.storage import load_dataset_df

                        validate_code(code)
                        df = load_dataset_df(dash["dataset_id"])
                        exec_res = execute_code(code, df)
                        if exec_res.get("success"):
                            w["result"] = exec_res.get("result_json", w.get("result"))
                            w["chart"] = exec_res.get("chart_json", w.get("chart"))
                    except Exception as e:
                        # Keep snapshot on failure
                        pass
            # Threshold check
            threshold = sched.get("threshold")
            if threshold and isinstance(threshold, dict):
                # e.g., {"pct":10, "metric": "Sales", "direction":"drop"}
                try:
                    pct = float(threshold.get("pct", 10))
                    direction = threshold.get("direction", "drop")
                    # Simple: sum of first widget's metric vs last run's sum stored in sched
                    # For now compare sum of last widget result's numeric column sum vs previous
                    total = 0
                    for w in dash.get("widgets", []):
                        res = w.get("result")
                        if res and res.get("data"):
                            # Sum numeric column
                            try:
                                import pandas as pd

                                df_tmp = (
                                    pd.DataFrame(res["data"])
                                    if isinstance(res["data"][0], dict)
                                    else pd.DataFrame(res["data"], columns=res["columns"])
                                )
                                num_cols = [
                                    c
                                    for c in df_tmp.columns
                                    if pd.api.types.is_numeric_dtype(df_tmp[c])
                                ]
                                if num_cols:
                                    total += pd.to_numeric(
                                        df_tmp[num_cols[0]], errors="coerce"
                                    ).sum()
                            except:
                                pass
                    last_total = sched.get("last_total")
                    sched["last_total"] = float(total)
                    _atomic_write_json(_schedule_path(sid), sched)
                    if last_total is not None and last_total != 0:
                        change_pct = (total - last_total) / last_total * 100
                        if direction == "drop" and change_pct <= -pct:
                            text_summary = f"Alert: {dashboard_id} dropped {abs(change_pct):.1f}% (threshold {pct}%) — {total:.0f} vs {last_total:.0f}"
                        elif direction == "increase" and change_pct >= pct:
                            text_summary = f"Alert: {dashboard_id} increased {change_pct:.1f}% (threshold {pct}%)"
                        else:
                            # Threshold not breached — optionally skip send?
                            text_summary = (
                                f"Checked: {dashboard_id} change {change_pct:.1f}% (no alert)"
                            )
                            # Still send? For now we send but note no alert
                            # If you want to skip, uncomment:
                            # _record_run(sid, "skipped", text_summary)
                            # return {"status":"skipped", "detail": text_summary}
                except Exception as e:
                    text_summary = f"Threshold check failed: {e}"

            # Generate PDF
            # Build share_url if dashboard is public
            if dash.get("share_slug") and dash.get("is_public"):
                # Need BACKEND_URL not available here, just build path
                share_url = f"/api/dashboards/share/{dash['share_slug']}"
            pdf_buf = dashboard_to_pdf(dash, share_url=share_url)
            text_summary = (
                text_summary
                or f"Dashboard '{dash['name']}' — {len(dash.get('widgets',[]))} widgets"
            )
        elif query and dataset_id:
            # Single query schedule
            from app.services.chat_service import process_query_v2
            import asyncio

            # process_query_v2 is async; run it
            try:
                loop = None
                import asyncio as _asyncio

                try:
                    loop = _asyncio.get_event_loop()
                except:
                    loop = None
                if loop and loop.is_running():
                    # In async context? just create task
                    import concurrent.futures as cf

                    with cf.ThreadPoolExecutor() as ex:
                        fut = ex.submit(_asyncio.run, process_query_v2(dataset_id, query))
                        res = fut.result(timeout=20)
                else:
                    res = _asyncio.run(process_query_v2(dataset_id, query))
            except Exception as e:
                # Fallback: if already in loop, use sync fallback via fallback_coder
                raise e
            # Build a simple PDF from single widget
            from app.core.exporter import dashboard_to_pdf

            fake_dash = {
                "name": sched.get("name", "Query Report"),
                "dataset_id": dataset_id,
                "description": f"Query: {query}",
                "share_slug": None,
                "is_public": False,
                "widgets": [
                    {
                        "title": query[:60],
                        "query": query,
                        "code": res.get("generated_code", ""),
                        "result": res.get("result"),
                        "chart": res.get("chart"),
                    }
                ],
            }
            pdf_buf = dashboard_to_pdf(fake_dash)
            text_summary = res.get("insight", "")[:300]
        else:
            raise ValueError("Schedule must have dashboard_id or (dataset_id+query)")

        # Send via channel
        pdf_bytes = pdf_buf.getvalue() if pdf_buf else None
        results = []
        channels = (
            [channel]
            if channel in ("email", "slack")
            else (["email", "slack"] if channel == "both" else [channel])
        )
        for ch in channels:
            if ch == "email":
                from app.core.senders import send_email

                subject = sched.get("name", "InsightAgent Report")
                body = f"{text_summary}\n\nSchedule {sid} • cron {sched.get('cron')}\nDashboard: {dashboard_id or query}\nGenerated at {sched.get('updated_at')}"
                attach = [("report.pdf", pdf_bytes, "application/pdf")] if pdf_bytes else []
                r = send_email(to_addr, subject, body, attachments=attach)
                results.append(r)
            elif ch == "slack":
                from app.core.senders import send_slack

                # to_addr for slack is webhook URL
                r = send_slack(to_addr, f"*{sched.get('name')}* — {text_summary}")
                # If we have pdf, we could try to send file via bot token — skip for webhook
                results.append(r)
        # Record success
        detail = "; ".join([str(r.get("status")) for r in results]) + f" — {text_summary[:200]}"
        _record_run(sid, "sent", detail, len(pdf_bytes) if pdf_bytes else 0)
        return {
            "status": "sent",
            "detail": detail,
            "channels": results,
            "pdf_bytes": len(pdf_bytes) if pdf_bytes else 0,
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        _record_run(sid, "error", str(e)[:300])
        raise


def run_schedule_now(sid: str) -> Dict[str, Any]:
    return run_schedule(sid)
