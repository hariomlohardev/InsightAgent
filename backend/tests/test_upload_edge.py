import tempfile
import uuid
from pathlib import Path
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app
from app.core import auth as auth_core

client = TestClient(app)


# auth for upload (anon is viewer after security fix)
def _auth_headers():
    email = f"u_{uuid.uuid4().hex[:6]}@example.com"
    try:
        u = auth_core.create_user(email, "TestPass123!", role="editor")
    except Exception:
        u = auth_core.get_user_by_email(email)
    return {"Authorization": f"Bearer {auth_core.create_jwt(u)}"}


_AUTH = _auth_headers()
# auto-auth wrapper (anon is viewer after fix)
_orig_post = client.post


def _post(*args, **kwargs):
    kwargs.setdefault("headers", _AUTH)
    # merge if caller passed headers
    if "headers" in kwargs and kwargs["headers"] is not _AUTH:
        # caller headers override, but keep auth if not present
        pass
    return _orig_post(*args, **kwargs)


client.post = _post
_orig_delete = client.delete


def _delete(*args, **kwargs):
    kwargs.setdefault("headers", _AUTH)
    return _orig_delete(*args, **kwargs)


client.delete = _delete
_orig_get = client.get


def _get(*args, **kwargs):
    # GET is viewer-allowed, but add auth to keep consistent
    kwargs.setdefault("headers", _AUTH)
    return _orig_get(*args, **kwargs)


client.get = _get


def test_upload_empty_file():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        tmp.write("")
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            r = client.post("/api/datasets/upload", files={"file": ("empty.csv", f, "text/csv")})
        assert r.status_code == 400
        assert "empty" in r.json()["detail"].lower()
    finally:
        tmp_path.unlink(missing_ok=True)


def test_upload_whitespace_only():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        tmp.write("   \n  \n")
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            r = client.post("/api/datasets/upload", files={"file": ("ws.csv", f, "text/csv")})
        assert r.status_code == 400
    finally:
        tmp_path.unlink(missing_ok=True)


def test_upload_unsupported_type():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as tmp:
        tmp.write("hello")
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            r = client.post("/api/datasets/upload", files={"file": ("test.txt", f, "text/plain")})
        assert r.status_code == 400
    finally:
        tmp_path.unlink(missing_ok=True)


def test_upload_malformed_csv():
    # CSV with unclosed quote
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        tmp.write('a,b\n1,"unclosed\n2,3\n')
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            r = client.post("/api/datasets/upload", files={"file": ("bad.csv", f, "text/csv")})
        # Should either 400 or 200 with some rows (pandas is lenient), but not 500
        assert r.status_code in [200, 400]
    finally:
        tmp_path.unlink(missing_ok=True)


def test_upload_sanitize_filename():
    df = pd.DataFrame({"A": [1, 2]})
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            # Try path traversal
            r = client.post(
                "/api/datasets/upload", files={"file": ("../../etc/passwd.csv", f, "text/csv")}
            )
        assert r.status_code == 200
        # Check that stored filename is sanitized
        data = r.json()
        assert ".." not in data["original_filename"]
        assert "/" not in data["original_filename"]
        # Cleanup
        client.delete(f"/api/datasets/{data['id']}")
    finally:
        tmp_path.unlink(missing_ok=True)


def test_upload_long_filename():
    df = pd.DataFrame({"A": [1, 2]})
    long_name = "a" * 200 + ".csv"
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            r = client.post("/api/datasets/upload", files={"file": (long_name, f, "text/csv")})
        assert r.status_code == 200
        assert len(r.json()["original_filename"]) <= 120
        client.delete(f"/api/datasets/{r.json()['id']}")
    finally:
        tmp_path.unlink(missing_ok=True)


def test_upload_json():
    import json

    data = [{"A": 1, "B": 2}, {"A": 3, "B": 4}]
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
        json.dump(data, open(tmp.name, "w"))
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            r = client.post(
                "/api/datasets/upload", files={"file": ("test.json", f, "application/json")}
            )
        assert r.status_code == 200
        assert r.json()["rows"] == 2
        client.delete(f"/api/datasets/{r.json()['id']}")
    finally:
        tmp_path.unlink(missing_ok=True)


def test_upload_excel():
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        df.to_excel(tmp.name, index=False)
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            r = client.post(
                "/api/datasets/upload",
                files={
                    "file": (
                        "test.xlsx",
                        f,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
        assert r.status_code == 200
        assert r.json()["rows"] == 2
        client.delete(f"/api/datasets/{r.json()['id']}")
    finally:
        tmp_path.unlink(missing_ok=True)


def test_download_endpoint():
    df = pd.DataFrame({"A": [1, 2]})
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            r = client.post("/api/datasets/upload", files={"file": ("dl.csv", f, "text/csv")})
        dataset_id = r.json()["id"]
        r = client.get(f"/api/datasets/{dataset_id}/download")
        assert r.status_code == 200
        assert "A" in r.text
        client.delete(f"/api/datasets/{dataset_id}")
    finally:
        tmp_path.unlink(missing_ok=True)


def test_list_pagination():
    # Ensure pagination works
    r = client.get("/api/datasets?limit=1&offset=0")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
