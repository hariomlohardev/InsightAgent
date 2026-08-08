import tempfile
from pathlib import Path
import pandas as pd
import os, json, time
from fastapi.testclient import TestClient

client = None

def get_client():
    global client
    if client is None:
        from app.main import app
        client = TestClient(app)
    return client

def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}

def test_auth_register_login_me():
    c = get_client()
    # Clean any old test users? Use unique email
    email = f"test_{int(time.time())}@example.com"
    pwd = "strongpass123"
    # register as editor (viewer cannot create api keys per RBAC)
    r = c.post("/api/auth/register", json={"email": email, "password": pwd, "role":"editor"})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    # login
    r2 = c.post("/api/auth/login", json={"email": email, "password": pwd})
    assert r2.status_code == 200, r2.text
    token = r2.json()["access_token"]
    assert token
    # me
    r3 = c.get("/api/auth/me", headers=_auth_headers(token))
    assert r3.status_code == 200
    assert r3.json()["email"] == email.lower()
    assert r3.json()["role"] == "editor"
    # api key
    r4 = c.post("/api/auth/api-key", json={"name":"mytoken"}, headers=_auth_headers(token))
    assert r4.status_code == 201, r4.text
    api_key = r4.json()["api_key"]
    assert api_key
    # Use api key
    r5 = c.get("/api/auth/me", headers={"X-API-Key": api_key})
    assert r5.status_code == 200
    # list keys
    r6 = c.get("/api/auth/api-key", headers=_auth_headers(token))
    assert r6.status_code == 200
    assert any(k["id"]==r4.json()["id"] for k in r6.json())
    # delete key
    r7 = c.delete(f"/api/auth/api-key/{r4.json()['id']}", headers=_auth_headers(token))
    assert r7.status_code == 200
    # invalid api key
    r8 = c.get("/api/auth/me", headers={"X-API-Key":"badkey123"})
    assert r8.status_code == 401

def test_admin_seed_and_rbac_viewer_blocked():
    c = get_client()
    # Login as admin (seeded)
    # Seed admin is admin@local / admin
    r = c.post("/api/auth/login", json={"email":"admin@local","password":"admin"})
    if r.status_code != 200:
        # try to register admin? Should already exist
        c.post("/api/auth/register", json={"email":"admin@local","password":"admin","role":"admin"})
        r = c.post("/api/auth/login", json={"email":"admin@local","password":"admin"})
    assert r.status_code == 200, r.text
    admin_token = r.json()["access_token"]
    # Create viewer user
    email_v = f"viewer_{int(time.time())}@example.com"
    c.post("/api/auth/register", json={"email": email_v, "password":"pass12345","role":"viewer"})
    r_v = c.post("/api/auth/login", json={"email": email_v, "password":"pass12345"})
    viewer_token = r_v.json()["access_token"]
    # Viewer cannot upload
    df = pd.DataFrame({"A":[1,2],"B":[3,4]})
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        df.to_csv(tmp.name, index=False)
        p = Path(tmp.name)
    with open(p, "rb") as f:
        r_up = c.post("/api/datasets/upload", files={"file":("test.csv", f, "text/csv")}, headers=_auth_headers(viewer_token))
    assert r_up.status_code == 403, r_up.text
    # Admin can upload
    with open(p, "rb") as f:
        r_up2 = c.post("/api/datasets/upload", files={"file":("test.csv", f, "text/csv")}, headers=_auth_headers(admin_token))
    assert r_up2.status_code == 200, r_up2.text
    did = r_up2.json()["id"]
    # Viewer can read (GET)
    r_get = c.get(f"/api/datasets/{did}", headers=_auth_headers(viewer_token))
    assert r_get.status_code == 200
    # Viewer cannot delete
    r_del = c.delete(f"/api/datasets/{did}", headers=_auth_headers(viewer_token))
    assert r_del.status_code == 403
    # Admin can delete
    r_del2 = c.delete(f"/api/datasets/{did}", headers=_auth_headers(admin_token))
    assert r_del2.status_code == 200
    Path(p).unlink(missing_ok=True)

def test_audit_log():
    c = get_client()
    # Login admin
    r = c.post("/api/auth/login", json={"email":"admin@local","password":"admin"})
    if r.status_code != 200:
        c.post("/api/auth/register", json={"email":"admin@local","password":"admin","role":"admin"})
        r = c.post("/api/auth/login", json={"email":"admin@local","password":"admin"})
    token = r.json()["access_token"]
    # Do an action
    df = pd.DataFrame({"A":[1],"B":[2]})
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        df.to_csv(tmp.name, index=False)
        p = Path(tmp.name)
    with open(p, "rb") as f:
        r_up = c.post("/api/datasets/upload", files={"file":("audit.csv", f, "text/csv")}, headers=_auth_headers(token))
    did = r_up.json()["id"]
    # Audit should contain it (admin only)
    r_aud = c.get("/api/audit", headers=_auth_headers(token))
    assert r_aud.status_code == 200, r_aud.text
    assert any("dataset.upload" in e.get("action","") for e in r_aud.json())
    # Viewer cannot access audit
    email_v = f"audit_viewer_{int(time.time())}@example.com"
    c.post("/api/auth/register", json={"email": email_v, "password":"pass12345"})
    r_v = c.post("/api/auth/login", json={"email": email_v, "password":"pass12345"})
    vt = r_v.json()["access_token"]
    r_aud2 = c.get("/api/audit", headers=_auth_headers(vt))
    assert r_aud2.status_code == 403
    c.delete(f"/api/datasets/{did}", headers=_auth_headers(token))
    Path(p).unlink(missing_ok=True)

def test_cache_and_polars_optional():
    # Cache hit test (in-memory fallback when REDIS_URL not set)
    from app.core.cache import set as cache_set, get as cache_get, cache_key
    ck = cache_key("test", "value")
    cache_set(ck, {"hello":"world"}, ttl=10)
    assert cache_get(ck) == {"hello":"world"}
    # Profiling cache
    from app.core.profiling import profile_dataframe
    df = pd.DataFrame({"A":[1,2,3],"B":[4,5,6]})
    prof1 = profile_dataframe(df)
    prof2 = profile_dataframe(df)
    assert prof1["shape"] == prof2["shape"]
    # Polars optional path (if polars installed, should not crash)
    import os
    os.environ["USE_POLARS"] = "true"
    try:
        from app.core.storage import load_dataset_df
        # upload then load with polars
        df2 = pd.DataFrame({"A":[1,2],"B":[3,4]})
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
            df2.to_csv(tmp.name, index=False)
            p = Path(tmp.name)
        c2 = get_client()
        login_r = c2.post("/api/auth/login", json={"email":"admin@local","password":"admin"})
        token_p = login_r.json()["access_token"]
        with open(p, "rb") as f:
            r = c2.post("/api/datasets/upload", files={"file":("polars.csv", f, "text/csv")}, headers=_auth_headers(token_p))
        did = r.json()["id"]
        # load via polars path
        loaded = load_dataset_df(did, use_polars=True)
        assert len(loaded) == 2
        c2.delete(f"/api/datasets/{did}", headers=_auth_headers(token_p))
        p.unlink(missing_ok=True)
    finally:
        os.environ.pop("USE_POLARS", None)

def test_queue_sync_fallback_without_redis():
    # Without REDIS_URL, forecast should be sync (200 not 202)
    # Ensure REDIS_URL not set
    old = os.environ.pop("REDIS_URL", None)
    try:
        c2 = get_client()
        # login as admin for upload (viewer/anon cannot upload)
        login_admin = c2.post("/api/auth/login", json={"email":"admin@local","password":"admin"})
        if login_admin.status_code != 200:
            c2.post("/api/auth/register", json={"email":"admin@local","password":"admin","role":"admin"})
            login_admin = c2.post("/api/auth/login", json={"email":"admin@local","password":"admin"})
        tok = login_admin.json()["access_token"]
        ah = _auth_headers(tok)
        df = pd.read_csv(Path(__file__).resolve().parents[2] / "sample_data/sales.csv")
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
            df.to_csv(tmp.name, index=False)
            p = Path(tmp.name)
        with open(p, "rb") as f:
            r = c2.post("/api/datasets/upload", files={"file":("sales.csv", f, "text/csv")}, headers=ah)
        assert r.status_code == 200, r.text
        did = r.json()["id"]
        # Forecast small data should be sync 200 when no REDIS
        r2 = c2.post("/api/chat", json={"dataset_id": did, "query":"forecast Sales for next 3 months"}, headers=ah)
        assert r2.status_code == 200, f"expected 200 sync, got {r2.status_code} {r2.text[:200]}"
        # With REDIS_URL set, it should be 202 for forecast (or fallback 200 if redis not reachable)
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"
        r3 = c2.post("/api/chat", json={"dataset_id": did, "query":"forecast Sales for next 3 months"}, headers=ah)
        assert r3.status_code in (200,202)
        if r3.status_code == 202:
            job_id = r3.json()["job_id"]
            r4 = c2.get(f"/api/jobs/{job_id}", headers=ah)
            assert r4.status_code in (200,404)
        c2.delete(f"/api/datasets/{did}", headers=ah)
        p.unlink(missing_ok=True)
    finally:
        if old:
            os.environ["REDIS_URL"] = old
        else:
            os.environ.pop("REDIS_URL", None)

def test_jobs_api_not_found():
    c2 = get_client()
    r = c2.get("/api/jobs/nonexist123")
    assert r.status_code == 404

def test_auth_anon_when_not_required():
    # Default AUTH_REQUIRED=false, anon should succeed for GET and POST (OSS frictionless, anon is editor)
    old = os.environ.get("AUTH_REQUIRED")
    os.environ["AUTH_REQUIRED"] = "false"
    try:
        # GET without token should succeed (anon editor)
        c2 = get_client()
        r = c2.get("/api/datasets")
        assert r.status_code == 200
        # POST without token should succeed when AUTH_REQUIRED=false (anon editor can upload)
        df = pd.DataFrame({"A":[1]})
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
            df.to_csv(tmp.name, index=False)
            p = Path(tmp.name)
        with open(p, "rb") as f:
            r2 = c2.post("/api/datasets/upload", files={"file":("anon.csv", f, "text/csv")})
        assert r2.status_code == 200, r2.text
        # cleanup uploaded dataset
        try:
            did2 = r2.json().get("id")
            if did2:
                c2.delete(f"/api/datasets/{did2}")
        except:
            pass
        p.unlink(missing_ok=True)
    finally:
        if old is None:
            os.environ.pop("AUTH_REQUIRED", None)
        else:
            os.environ["AUTH_REQUIRED"] = old
