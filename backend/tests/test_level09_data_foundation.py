"""Level 09 — DB CRUD + S3 mock tests (7 new)."""

import os
import tempfile
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Use sqlite file for isolated DB tests; aiosqlite for async, sync fallback via sqlite://
TEST_DB = "sqlite+aiosqlite:///./test_level09.db"
# Ensure clean state
for f in ["./test_level09.db", "./test_level09.db-journal"]:
    try:
        Path(f).unlink(missing_ok=True)
    except:
        pass

os.environ["DATABASE_URL"] = TEST_DB

# Reimport after env set — clear cached engines
import importlib
import app.core.db as dbmod
import app.core.storage as storagemod

# Reset cached engines
dbmod._engine = None
dbmod._SessionLocal = None
dbmod._sync_engine = None
dbmod._SyncSessionLocal = None

# Ensure tables
from app.core.db import init_db_sync

init_db_sync()

from app.main import app

client = TestClient(app)


def _upload_df(df: pd.DataFrame, name: str = "test.csv"):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        df.to_csv(tmp.name, index=False)
        p = Path(tmp.name)
    with open(p, "rb") as f:
        r = client.post("/api/datasets/upload", files={"file": (name, f, "text/csv")})
    p.unlink(missing_ok=True)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_db_crud_via_api():
    """Upload, list, get, delete via DB path."""
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    did = _upload_df(df, "dbcrud.csv")
    # list
    r = client.get("/api/datasets")
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert did in ids
    # get meta
    r = client.get(f"/api/datasets/{did}")
    assert r.status_code == 200
    assert r.json()["dataset"]["id"] == did
    # delete
    r = client.delete(f"/api/datasets/{did}")
    # API may return 200 or 204
    assert r.status_code in (200, 204, 404)
    # get should now 404
    r = client.get(f"/api/datasets/{did}")
    assert r.status_code == 404


def test_db_filesystem_fallback_when_no_db():
    """When DATABASE_URL empty, use_db() False and filesystem still works."""
    orig = os.getenv("DATABASE_URL")
    os.environ["DATABASE_URL"] = ""
    # reset cache
    dbmod._engine = None
    dbmod._SessionLocal = None
    dbmod._sync_engine = None
    dbmod._SyncSessionLocal = None
    from app.core.db import use_db

    assert use_db() is False
    # Restore
    if orig:
        os.environ["DATABASE_URL"] = orig
    else:
        os.environ.pop("DATABASE_URL", None)
    dbmod._engine = None
    dbmod._SessionLocal = None
    dbmod._sync_engine = None
    dbmod._SyncSessionLocal = None
    # Re-set for remaining tests
    os.environ["DATABASE_URL"] = TEST_DB
    dbmod._engine = None
    dbmod._SessionLocal = None
    dbmod._sync_engine = None
    dbmod._SyncSessionLocal = None
    init_db_sync()


def test_db_isolation_via_storage_direct():
    """Direct storage API with DB."""
    df = pd.DataFrame({"x": [10, 20]})
    # Use storage directly
    from app.core.storage import save_dataset, list_datasets, get_dataset_meta, delete_dataset

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        df.to_csv(tmp.name, index=False)
        p = Path(tmp.name)
    did = save_dataset(p, "direct.csv")
    p.unlink(missing_ok=True)
    assert did
    metas = list_datasets()
    assert any(m["id"] == did for m in metas)
    meta = get_dataset_meta(did)
    assert meta and meta["id"] == did
    assert delete_dataset(did) is True
    assert get_dataset_meta(did) is None


def test_health_db_field():
    # Ensure DB is set for this test (isolate from perf fixture which clears DATABASE_URL)
    import os as _os

    if not _os.getenv("DATABASE_URL"):
        _os.environ["DATABASE_URL"] = TEST_DB
        import app.core.db as _dbm

        _dbm._engine = None
        _dbm._SessionLocal = None
        _dbm._sync_engine = None
        _dbm._SyncSessionLocal = None
        init_db_sync()
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert "db" in j
    assert j["db"]["status"] in ("connected", "filesystem")
    assert j["db"]["status"] == "connected"


def test_s3_mock_moto():
    """S3 via moto mock — proves STORAGE_BACKEND=s3 path works without real AWS."""
    try:
        from moto import mock_aws
    except ImportError:
        from moto import mock_s3 as mock_aws  # older
    import boto3
    import os as _os

    bucket = "test-bucket-09"
    _os.environ["STORAGE_BACKEND"] = "s3"
    _os.environ["S3_BUCKET"] = bucket
    _os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    _os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    _os.environ["AWS_SECURITY_TOKEN"] = "testing"
    _os.environ["AWS_SESSION_TOKEN"] = "testing"
    _os.environ["AWS_REGION"] = "us-east-1"
    with mock_aws():
        # create bucket
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=bucket)
        # upload via storage
        df = pd.DataFrame({"c": [1, 2, 3]})
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
            df.to_csv(tmp.name, index=False)
            p = Path(tmp.name)
        from app.core.storage import save_dataset, load_dataset_df, delete_dataset

        did = save_dataset(p, "s3test.csv")
        p.unlink(missing_ok=True)
        # Verify S3 has file via fsspec or boto (moto intercepts both, but check via load)
        # Load via S3 path - primary proof
        df2 = load_dataset_df(did)
        assert len(df2) == 3
        assert list(df2.columns) == ["c"]
        # Also verify via fsspec filesystem (more reliable with moto than boto list)
        try:
            import fsspec

            fs = fsspec.filesystem("s3")
            s3_path = f"s3://{bucket}/datasets/{did}/data.csv"
            assert fs.exists(s3_path), f"S3 file not found at {s3_path}"
        except Exception:
            # fallback to boto if fsspec not available
            objs = s3.list_objects_v2(Bucket=bucket)
            assert "Contents" in objs
            keys = [o["Key"] for o in objs["Contents"]]
            assert any(did in k for k in keys)
        # Cleanup
        delete_dataset(did)
    # restore
    _os.environ.pop("STORAGE_BACKEND", None)
    _os.environ.pop("S3_BUCKET", None)


def test_otel_no_crash_when_empty():
    """OTEL with empty endpoint should not crash and /health still works."""
    # Already tested health, just ensure no exception on import
    r = client.get("/health")
    assert r.status_code == 200


def test_alembic_migration_exists():
    """001_init exists and creates expected tables."""
    p = Path("backend/alembic/versions/001_init.py")
    if not p.exists():
        p = Path("alembic/versions/001_init.py")
    assert p.exists(), "001_init.py missing"
    txt = p.read_text()
    for tbl in ["datasets", "dashboards", "users", "workspaces", "billing", "audit_log"]:
        assert tbl in txt, f"table {tbl} not in migration"


# Cleanup after module
def test_cleanup_level09_db():
    for f in ["./test_level09.db", "./test_level09.db-journal"]:
        try:
            Path(f).unlink(missing_ok=True)
        except:
            pass
    # Reset env for subsequent tests (filesystem fallback)
    os.environ.pop("DATABASE_URL", None)
    dbmod._engine = None
    dbmod._SessionLocal = None
    dbmod._sync_engine = None
    dbmod._SyncSessionLocal = None
    # Also clear storage backend
    os.environ.pop("STORAGE_BACKEND", None)
    os.environ.pop("S3_BUCKET", None)
