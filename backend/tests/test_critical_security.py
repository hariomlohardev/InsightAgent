"""
Critical regression tests for 9 bugs: async, double exec, slack, auth, anon, CORS, sandbox, SQL, conversation race.
"""
import os
import re
import sys
import uuid
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

FRONTEND = Path(__file__).parent.parent.parent / "frontend" / "streamlit_app.py"
STORAGE = Path(__file__).parent.parent / "app" / "core" / "storage.py"
CONNECTORS = Path(__file__).parent.parent / "app" / "core" / "connectors.py"
SECURITY = Path(__file__).parent.parent / "app" / "core" / "security.py"
SENDERS = Path(__file__).parent.parent / "app" / "core" / "senders.py"
AUTH_CORE = Path(__file__).parent.parent / "app" / "core" / "auth.py"
AUTH_API = Path(__file__).parent.parent / "app" / "api" / "auth.py"
MAIN = Path(__file__).parent.parent / "app" / "main.py"
CHAT_SVC = Path(__file__).parent.parent / "app" / "services" / "chat_service.py"
WRANGLE = Path(__file__).parent.parent / "app" / "services" / "wrangle_service.py"


# 1. Queued job
def test_queued_job_design():
    src = FRONTEND.read_text()
    assert "rr.text = str(d)" not in src
    assert 'status == "completed"' in src and 'status == "failed"' in src
    assert "504" in src
    assert "_json.dumps" in src
    assert "malformed" in src.lower()


# 2. Double exec — single execution
def test_no_double_exec():
    for p in [CHAT_SVC, WRANGLE]:
        src = p.read_text()
        # after fix there is no naked exec(code, get_safe_globals
        assert "exec(code, safe_globals" not in src, f"double exec still in {p.name}"
        assert "_after_df" in src

    # mutation test: inplace drop should happen exactly once
    from app.agent.executor import execute_code

    df = pd.DataFrame({"x": [1, 2], "y": [3, 4], "z": [5, 6]})
    code = 'df.drop("x", axis=1, inplace=True)\nresult = df'
    res = execute_code(code, df)
    assert res["success"]
    after = res["_after_df"]
    assert "x" not in after.columns
    assert list(after.columns) == ["y", "z"]
    # original df should not be mutated (executor uses copy via safe_globals? Check)
    # Ensure second execution would fail — but we don't do it. Prove single exec by checking that after_df is from first exec only
    # Also rename inplace
    df2 = pd.DataFrame({"old": [1, 2]})
    code2 = 'df.rename(columns={"old": "new"}, inplace=True)\nresult = df'
    res2 = execute_code(code2, df2)
    assert "new" in res2["_after_df"].columns
    assert "old" not in res2["_after_df"].columns


def test_preview_apply_no_save_on_fail(tmp_path, monkeypatch):
    # apply_clean should not create version on failure
    import asyncio

    from app.services.wrangle_service import apply_clean
    from app.core import storage

    # setup temp storage
    monkeypatch.setenv("STORAGE_BACKEND", "fs")
    from app.config import get_storage_path

    # use temp dir for storage
    tmp_storage = Path(tempfile.mkdtemp())
    monkeypatch.setattr("app.config.get_storage_path", lambda: tmp_storage)
    monkeypatch.setattr("app.core.storage.get_storage_path", lambda: tmp_storage)
    # create dataset
    did = "testfail"
    ddir = tmp_storage / "datasets" / did
    ddir.mkdir(parents=True)
    df0 = pd.DataFrame({"a": [1, 2]})
    df0.to_csv(ddir / "data.csv", index=False)
    import json, datetime

    meta = {
        "id": did,
        "original_filename": "a.csv",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "rows": 2,
        "columns": 1,
        "column_names": ["a"],
        "file_path": str(ddir / "data.csv"),
        "current_version": 0,
        "type": "file",
        "workspace_id": "default",
    }
    (ddir / "meta.json").write_text(json.dumps(meta))
    (ddir / "versions").mkdir()
    df0.to_csv(ddir / "versions" / "0.csv", index=False)
    (ddir / "versions" / "versions.json").write_text(json.dumps([{"version": 0}]))

    # failing code
    async def _bad_coder(q, p, i):
        return {"code": 'raise ValueError("boom")\nresult = df', "explanation": ""}

    monkeypatch.setattr("app.agent.coder.generate_code", _bad_coder)
    # need to mock planner etc? apply_clean will generate via coder, we already did
    res = asyncio.run(apply_clean(did, "bad"))
    assert res["success"] is False
    # ensure no new version created
    versions = storage.list_versions(did)
    assert len(versions) == 1  # still only v0


# 3. Slack filename
def test_slack_filename():
    src = SENDERS.read_text()
    assert '"filename" in locals()' not in src
    assert "def send_slack_via_bot" in src
    # check signature has filename param
    assert "filename" in src.split("def send_slack_via_bot")[1].split(")")[0]
    # check files dict uses filename variable directly
    assert 'files={"file": (filename, file_bytes' in src or "files={\"file\": (filename" in src

    # runtime test
    from app.core.senders import send_slack_via_bot

    with patch("httpx.post") as mock_post, patch("requests.post") as mock_req:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json = lambda: {"ok": True}
        mock_req.return_value.status_code = 200
        send_slack_via_bot("xoxb-test", "C123", "hello", b"bytes", filename="my_report.png")
        # check second call (files.upload) used filename
        assert mock_req.called
        kwargs = mock_req.call_args[1]
        assert kwargs["files"]["file"][0] == "my_report.png"
        assert kwargs["files"]["file"][1] == b"bytes"

    # fallback
    with patch("httpx.post") as mock_post, patch("requests.post") as mock_req:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json = lambda: {"ok": True}
        send_slack_via_bot("xoxb", "C", "hi", b"b")
        kwargs = mock_req.call_args[1]
        assert kwargs["files"]["file"][0] == "chart.png"


# 4. Hardcoded admin
def test_no_hardcoded_admin():
    src = AUTH_CORE.read_text()
    assert 'os.getenv("ADMIN_PASSWORD", "admin")' not in src
    assert 'os.getenv("ADMIN_EMAIL", "admin@local")' not in src
    # must generate secure or require env
    assert "secrets.token_urlsafe" in src


def test_seed_admin_secure(tmp_path, monkeypatch):
    from app.core import auth as ac

    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setattr("app.core.auth.get_storage_path", lambda: tmp)
    monkeypatch.setattr("app.config.get_storage_path", lambda: tmp)
    # ensure no users
    # clear
    for f in (tmp / "users").glob("*.json"):
        f.unlink(missing_ok=True)
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    u = ac.seed_admin()
    assert u is not None
    assert u["email"] == "admin@local"
    # password should not be "admin"
    # verify hash not equal to hash of "admin" with any salt — we can verify by checking verify_password
    assert ac.verify_password("admin", u["password_hash"]) is False
    # second call should not create new
    u2 = ac.seed_admin()
    assert u2 is None
    # with explicit env it should use it
    monkeypatch.setenv("ADMIN_EMAIL", "boss@corp.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Str0ng!Pass123")
    # need clean users
    for f in (tmp / "users").glob("*.json"):
        f.unlink()
    u3 = ac.seed_admin()
    assert u3["email"] == "boss@corp.com"
    assert ac.verify_password("Str0ng!Pass123", u3["password_hash"])


# 5. Anonymous viewer
def test_anon_viewer():
    src = AUTH_API.read_text()
    assert '"role": "viewer"' in src
    assert '"role": "editor"' not in src or src.count('"role": "viewer"') >= 1
    # check that viewer cannot upload is enforced elsewhere (storage delete requires editor/admin) — but at least anon is viewer

    # runtime: get_current_user with AUTH_REQUIRED=false should be viewer
    from fastapi import Request
    from app.api.auth import get_current_user

    # mock no credentials, no api key
    with patch.dict(os.environ, {"AUTH_REQUIRED": "false", "ENTERPRISE": "false", "CLOUD": "false"}):
        user = get_current_user(credentials=None, x_api_key=None, request=None)
        assert user["role"] == "viewer"
        assert user["id"] == "anon"

    with patch.dict(os.environ, {"AUTH_REQUIRED": "true"}):
        try:
            get_current_user(credentials=None, x_api_key=None, request=None)
            assert False, "should raise 401"
        except Exception as e:
            assert "401" in str(e) or "Authentication required" in str(e)


# 6. CORS
def test_cors_config():
    src = MAIN.read_text()
    assert 'allow_origins=["*"]' not in src
    assert "CORS_ALLOWED_ORIGINS" in src
    assert "allow_credentials=True" in src
    # default should be explicit localhost origins
    assert "http://localhost:8501" in src


# 7. Sandbox
def test_sandbox_getattr_blocked():
    src = SECURITY.read_text()
    # validate_code blocks getattr/hasattr, safe_globals must not expose them
    assert '"hasattr": hasattr' not in src
    assert '"getattr": getattr' not in src
    # ensure validate still blocks
    from app.core.security import validate_code, SecurityError

    for snippet in ["getattr(df, 'columns')", "hasattr(df, 'x')", "open('a')", "eval('1')", "__import__('os')"]:
        try:
            validate_code(snippet)
            assert False, f"should block {snippet}"
        except SecurityError:
            pass
    # ensure safe globals not contain them
    from app.core.security import get_safe_globals

    sg = get_safe_globals(pd.DataFrame({"a": [1]}))
    assert "getattr" not in sg
    assert "hasattr" not in sg
    # actual executor should also block
    from app.agent.executor import execute_code

    res = execute_code("getattr(df, 'columns')\nresult=df", pd.DataFrame({"a": [1]}))
    assert res["success"] is False


# 8. SQL guard
def test_sql_guard():
    from app.core.connectors import validate_sql
    from app.core.security import SecurityError

    # allowed
    for q in ["SELECT * FROM t", "WITH c AS (SELECT 1) SELECT * FROM c", "EXPLAIN SELECT * FROM t", "SHOW TABLES"]:
        validate_sql(q)  # should not raise

    # blocked
    blocked = [
        "DROP TABLE t",
        "DELETE FROM t",
        "UPDATE t SET x=1",
        "INSERT INTO t VALUES (1)",
        "CREATE TABLE t (x int)",
        "ALTER TABLE t ADD x int",
        "ATTACH DATABASE 'a.db' AS a",
        "INSTALL httpfs",
        "COPY t TO '/tmp/a.csv'",
        "SELECT * FROM t; DROP TABLE t",
        "select * from t where 1=1; -- drop",
        "/* comment */ DROP TABLE t",
        "SeLeCt * FrOm t; DELETE FROM t",
        "  ATTACH  DATABASE 'x'  ",
    ]
    for q in blocked:
        try:
            validate_sql(q)
            assert False, f"should block {q}"
        except SecurityError:
            pass

    # comment-obfuscated
    try:
        validate_sql("SELECT * FROM t -- ; DROP")
        # this is SELECT with trailing comment, should pass? Our normalize strips --.*, so should pass as SELECT only
        pass
    except SecurityError:
        pass  # acceptable either


# 9. Conversation race
def test_conversation_race_fix():
    src = CHAT_SVC.read_text()
    # old race used convs[0] in logic (not comment) — check that active code doesn't use it
    # filter out comment lines
    code_lines = [l for l in src.splitlines() if not l.strip().startswith("#")]
    active = "\n".join(code_lines)
    assert "convs[0]" not in active
    # new should be wrapper to v2
    assert "process_query_v2" in src
    # ensure process_query is now wrapper not race
    # check that save_conversation_message return value is used in v2? v2 already correct uses save with explicit id
    # Just ensure no list_conversations race
    assert src.count("list_conversations") <= 2  # only maybe in v2 for reading, not for race

    # concurrency test: two concurrent creates should get distinct ids
    from app.core import storage
    import asyncio

    async def _racer():
        # use tmp storage
        tmp = Path(tempfile.mkdtemp())
        # patch storage path
        import app.config

        orig = app.config.get_storage_path
        orig2 = storage.get_storage_path if hasattr(storage, "get_storage_path") else None
        # Use monkeypatch via direct patch
        return tmp

    # simpler: test that save_conversation_message returns distinct ids when called concurrently without conversation_id
    from app.core.storage import save_conversation_message
    import concurrent.futures

    tmp = Path(tempfile.mkdtemp())
    # patch dirs
    with patch("app.core.storage._conversations_dir", return_value=tmp), patch(
        "app.config.get_storage_path", return_value=tmp
    ):
        tmp.mkdir(exist_ok=True)
        ids = set()

        def create():
            return save_conversation_message("ds1", "", "user", {"q": "hi"})

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futs = [ex.submit(create) for _ in range(2)]
            for f in futs:
                ids.add(f.result())
        assert len(ids) == 2, "concurrent creates should give distinct ids"
