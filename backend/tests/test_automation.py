import tempfile
from pathlib import Path
import pandas as pd
import time, hmac, hashlib, os, json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _upload_df(df: pd.DataFrame, name="test.csv"):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        df.to_csv(tmp.name, index=False)
        p = Path(tmp.name)
    with open(p, "rb") as f:
        r = client.post("/api/datasets/upload", files={"file": (name, f, "text/csv")})
    Path(p).unlink()
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _make_dashboard():
    df = pd.read_csv(Path(__file__).resolve().parents[2] / "sample_data/sales.csv")
    did = _upload_df(df, "sales.csv")
    r = client.post("/api/dashboards", json={"dataset_id": did, "name": "Test Dash"})
    dash_id = r.json()["id"]
    # add widget
    rw = client.post(
        f"/api/dashboards/{dash_id}/widgets",
        json={
            "query": "q",
            "code": "result = df.head(2)",
            "result": {"columns": ["A"], "data": [[1], [2]]},
            "chart": None,
            "title": "W1",
        },
    )
    assert rw.status_code == 200
    return did, dash_id, rw.json()["id"]


def test_schedule_create_list_run_delete():
    try:
        import apscheduler  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("apscheduler not installed")
    did, dash_id, wid = _make_dashboard()
    # create schedule
    r = client.post(
        "/api/schedules",
        json={
            "dashboard_id": dash_id,
            "cron": "0 9 * * 1",
            "channel": "email",
            "to": "test@example.com",
            "name": "Weekly",
        },
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    # invalid cron
    r_bad = client.post(
        "/api/schedules",
        json={"dashboard_id": dash_id, "cron": "bad", "channel": "email", "to": "a@b.com"},
    )
    assert r_bad.status_code == 400
    # list
    r2 = client.get("/api/schedules")
    assert any(s["id"] == sid for s in r2.json())
    # get
    r3 = client.get(f"/api/schedules/{sid}")
    assert r3.status_code == 200
    # run now (simulated)
    # mock SMTP by not setting env (already simulated)
    r4 = client.post(f"/api/schedules/{sid}/run")
    assert r4.status_code == 200, r4.text
    assert r4.json()["status"] == "sent"
    assert r4.json()["pdf_bytes"] > 1000
    # runs
    r5 = client.get(f"/api/schedules/{sid}/runs")
    assert len(r5.json()["runs"]) >= 1
    # export pdf
    r6 = client.get(f"/api/schedules/{sid}/export")
    assert r6.status_code == 200
    assert r6.headers["content-type"] == "application/pdf"
    assert len(r6.content) > 1000
    # query-based schedule
    rq = client.post(
        "/api/schedules",
        json={
            "query": "Show top 5 products",
            "dataset_id": did,
            "cron": "0 9 * * *",
            "channel": "email",
            "to": "q@example.com",
            "name": "Q sched",
        },
    )
    assert rq.status_code == 201, rq.text
    q_sid = rq.json()["id"]
    r_qrun = client.post(f"/api/schedules/{q_sid}/run")
    assert r_qrun.status_code == 200
    client.delete(f"/api/schedules/{q_sid}")
    # threshold schedule
    r_thr = client.post(
        "/api/schedules",
        json={
            "dashboard_id": dash_id,
            "cron": "*/5 * * * *",
            "channel": "slack",
            "to": "https://hooks.slack.com/services/test",
            "name": "Thr",
            "threshold": {"pct": 10, "direction": "drop"},
        },
    )
    assert r_thr.status_code == 201
    sid_thr = r_thr.json()["id"]
    r_thr_run = client.post(f"/api/schedules/{sid_thr}/run")
    assert r_thr_run.status_code == 200
    client.delete(f"/api/schedules/{sid_thr}")
    # delete
    r7 = client.delete(f"/api/schedules/{sid}")
    assert r7.status_code == 200
    assert client.get(f"/api/schedules/{sid}").status_code == 404
    # cleanup
    client.delete(f"/api/dashboards/{dash_id}")
    client.delete(f"/api/datasets/{did}")


def test_exporter_pdf():
    try:
        import reportlab  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("reportlab not installed")
    did, dash_id, wid = _make_dashboard()
    r = client.get(f"/api/dashboards/{dash_id}/export?format=pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 1500
    # with chart
    # add chart widget
    chart = {
        "data": [{"x": ["A", "B"], "y": [1, 2], "type": "bar"}],
        "layout": {"title": {"text": "My Chart"}},
    }
    rw2 = client.post(
        f"/api/dashboards/{dash_id}/widgets",
        json={
            "query": "q2",
            "code": "result = df.head(2)",
            "result": {"columns": ["A", "B"], "data": [[1, 2], [3, 4]]},
            "chart": chart,
            "title": "WithChart",
        },
    )
    assert rw2.status_code == 200
    r2 = client.get(f"/api/dashboards/{dash_id}/export?format=pdf")
    assert r2.status_code == 200
    assert len(r2.content) > 1500
    client.delete(f"/api/dashboards/{dash_id}")
    client.delete(f"/api/datasets/{did}")


def test_senders_mock(monkeypatch=None):
    # Test send_email simulated when no env
    from app.core.senders import send_email, send_slack
    import os

    os.environ.pop("SMTP_HOST", None)
    r = send_email("to@example.com", "Subject", "Body")
    assert r["status"] == "simulated"
    # Simulated slack
    os.environ.pop("SLACK_WEBHOOK_URL", None)
    r2 = send_slack("", "hello")
    assert r2["status"] == "simulated"
    # With webhook URL but mock httpx? We test real path but without network we expect error or sent
    # We'll just check that function exists and doesn't crash
    r3 = send_slack("https://hooks.slack.com/services/fake", "test")
    assert r3["status"] in ("sent", "error", "simulated")


def test_slack_events():
    os.environ["SLACK_SIGNING_SECRET"] = "testsecret123"
    os.environ["SLACK_VERIFY"] = "true"
    # url_verification
    r = client.post("/api/slack/events", json={"type": "url_verification", "challenge": "ch123"})
    assert r.status_code == 200
    assert "ch123" in r.text
    # valid app_mention
    import time, hmac, hashlib, json as _json

    body = _json.dumps(
        {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "text": "<@U123> hello",
                "channel": "C123",
                "user": "U456",
            },
        }
    ).encode()
    ts = str(int(time.time()))
    basestring = f"v0:{ts}:{body.decode()}"
    sig = "v0=" + hmac.new(b"testsecret123", basestring.encode(), hashlib.sha256).hexdigest()
    r2 = client.post(
        "/api/slack/events",
        content=body,
        headers={
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json().get("status") in ("ok (no token)", "sent", "ok", "no dataset", "slack error")
    # invalid sig
    r3 = client.post(
        "/api/slack/events",
        content=body,
        headers={
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": "v0=bad",
            "Content-Type": "application/json",
        },
    )
    assert r3.status_code == 401
    # old timestamp (>5min)
    old_ts = str(int(time.time()) - 400)
    old_sig = (
        "v0="
        + hmac.new(
            b"testsecret123", f"v0:{old_ts}:{body.decode()}".encode(), hashlib.sha256
        ).hexdigest()
    )
    r4 = client.post(
        "/api/slack/events",
        content=body,
        headers={"X-Slack-Request-Timestamp": old_ts, "X-Slack-Signature": old_sig},
    )
    assert r4.status_code == 401
    # Missing sig
    os.environ["SLACK_VERIFY"] = "false"
    r5 = client.post("/api/slack/events", content=body)
    # When verify false, should not require sig, returns ok
    assert r5.status_code == 200
    os.environ["SLACK_VERIFY"] = "true"
    os.environ.pop("SLACK_SIGNING_SECRET", None)


def test_comments():
    did, dash_id, wid = _make_dashboard()
    # post
    r = client.post(f"/api/dashboards/{dash_id}/comments", json={"text": "Nice!", "user": "alice"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    # list
    r2 = client.get(f"/api/dashboards/{dash_id}/comments")
    assert len(r2.json()) == 1
    # reply threaded
    r3 = client.post(
        f"/api/dashboards/{dash_id}/comments",
        json={"text": "Reply", "user": "bob", "parent_id": cid},
    )
    assert r3.status_code == 201
    r4 = client.get(f"/api/dashboards/{dash_id}/comments")
    assert len(r4.json()) == 2
    # delete
    r5 = client.delete(f"/api/dashboards/{dash_id}/comments/{cid}")
    assert r5.status_code == 200
    r6 = client.get(f"/api/dashboards/{dash_id}/comments")
    assert len(r6.json()) == 1
    # 404
    assert client.delete(f"/api/dashboards/{dash_id}/comments/bad123").status_code == 404
    assert client.post(f"/api/dashboards/bad123/comments", json={"text": "hi"}).status_code == 404
    # empty text
    assert (
        client.post(f"/api/dashboards/{dash_id}/comments", json={"text": "   "}).status_code == 400
    )
    client.delete(f"/api/dashboards/{dash_id}")
    client.delete(f"/api/datasets/{did}")


def test_reports():
    try:
        import reportlab  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("reportlab not installed")
    did, dash_id, wid = _make_dashboard()
    # create report with markdown + widget
    r = client.post(
        "/api/reports",
        json={
            "dashboard_id": dash_id,
            "name": "QBR",
            "description": "desc",
            "blocks": [
                {"type": "markdown", "text": "# Header\nHello"},
                {"type": "widget", "widget_id": wid},
            ],
        },
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    # list
    r2 = client.get("/api/reports")
    assert any(rep["id"] == rid for rep in r2.json())
    # get
    r3 = client.get(f"/api/reports/{rid}")
    assert r3.status_code == 200
    # export pdf
    r4 = client.get(f"/api/reports/{rid}/export?format=pdf")
    assert r4.status_code == 200
    assert len(r4.content) > 1000
    # export json
    r5 = client.get(f"/api/reports/{rid}/export?format=json")
    assert r5.status_code == 200
    assert r5.json()["id"] == rid
    # export csv
    r6 = client.get(f"/api/reports/{rid}/export?format=csv")
    assert r6.status_code == 200
    assert r6.headers["content-type"] == "application/zip"
    # delete
    r7 = client.delete(f"/api/reports/{rid}")
    assert r7.status_code == 200
    assert client.get(f"/api/reports/{rid}").status_code == 404
    # invalid widget
    r_bad = client.post(
        "/api/reports",
        json={
            "dashboard_id": dash_id,
            "name": "Bad",
            "blocks": [{"type": "widget", "widget_id": "bad123"}],
        },
    )
    assert r_bad.status_code == 400
    client.delete(f"/api/dashboards/{dash_id}")
    client.delete(f"/api/datasets/{did}")


def test_schedule_threshold_and_both_channel():
    try:
        import apscheduler  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("apscheduler not installed")
    did, dash_id, wid = _make_dashboard()
    # both channels
    r = client.post(
        "/api/schedules",
        json={
            "dashboard_id": dash_id,
            "cron": "0 9 * * *",
            "channel": "both",
            "to": "test@example.com",
            "name": "Both",
        },
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    r2 = client.post(f"/api/schedules/{sid}/run")
    assert r2.status_code == 200
    assert r2.json()["status"] == "sent"
    # ensure runs recorded
    r3 = client.get(f"/api/schedules/{sid}/runs")
    assert len(r3.json()["runs"]) >= 1
    client.delete(f"/api/schedules/{sid}")
    client.delete(f"/api/dashboards/{dash_id}")
    client.delete(f"/api/datasets/{did}")
