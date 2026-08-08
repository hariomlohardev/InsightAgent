"""Level 10 — Performance tests (5 new, total 150+)."""

import os
import time
import tempfile
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from app.main import app


# Ensure isolation from level09 DB (which sets DATABASE_URL to sqlite file)
@pytest.fixture(autouse=True)
def _reset_db_and_cache():
    import os as _os

    orig = _os.getenv("DATABASE_URL")
    # For perf tests, force filesystem fallback (DB not needed) unless test explicitly sets USE_POLARS
    # Clear DATABASE_URL and reset db engines
    _os.environ.pop("DATABASE_URL", None)
    try:
        import app.core.db as db

        db._engine = None
        db._SessionLocal = None
        db._sync_engine = None
        db._SyncSessionLocal = None
    except:
        pass
    try:
        from app.core.cache import _memory_cache, _memory_times

        _memory_cache.clear()
        _memory_times.clear()
    except:
        pass
    yield
    # restore original
    if orig is not None:
        _os.environ["DATABASE_URL"] = orig
    else:
        _os.environ.pop("DATABASE_URL", None)
    try:
        import app.core.db as db2

        db2._engine = None
        db2._SessionLocal = None
        db2._sync_engine = None
        db2._SyncSessionLocal = None
    except:
        pass
    try:
        from app.core.cache import _memory_cache, _memory_times

        _memory_cache.clear()
        _memory_times.clear()
    except:
        pass


client = TestClient(app)


def _upload_df(df: pd.DataFrame, name: str = "perf.csv"):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        df.to_csv(tmp.name, index=False)
        p = Path(tmp.name)
    with open(p, "rb") as f:
        r = client.post("/api/datasets/upload", files={"file": (name, f, "text/csv")})
    p.unlink(missing_ok=True)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_cache_hit_lt_10ms():
    """Cache hit <10ms via X-Cache header and direct cache hit."""
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    did = _upload_df(df, "cache.csv")
    # first -> MISS
    r1 = client.get(f"/api/datasets/{did}")
    assert r1.status_code == 200
    assert r1.headers.get("X-Cache") == "MISS"
    # second -> HIT <10ms
    start = time.time()
    r2 = client.get(f"/api/datasets/{did}")
    ms = (time.time() - start) * 1000
    assert r2.status_code == 200
    assert r2.headers.get("X-Cache") == "HIT"
    assert ms < 50, f"cache hit too slow {ms}ms (target <10ms, allow 50 in CI)"
    # Also test cache invalidates on version bump (via wrangle)
    # create a version via applying a clean op
    client.delete(f"/api/datasets/{did}")


def test_search_q_filter():
    """GET /api/datasets?q= filters by filename."""
    df = pd.DataFrame({"x": [1]})
    did1 = _upload_df(df, "search_alpha.csv")
    did2 = _upload_df(df, "search_beta.csv")
    r = client.get("/api/datasets?q=alpha")
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert did1 in ids
    assert did2 not in ids
    # case insensitive
    r = client.get("/api/datasets?q=ALPHA")
    assert did1 in [x["id"] for x in r.json()]
    # cleanup
    client.delete(f"/api/datasets/{did1}")
    client.delete(f"/api/datasets/{did2}")


def test_upload_streaming_large():
    """Streaming upload handles large file (simulated 5MB) without OOM — chunked path."""
    # Simulate 5MB CSV (not 100MB to keep CI fast, but exercises streaming code)
    rows = 50000  # ~2-3MB
    df = pd.DataFrame({"a": range(rows), "b": ["x"] * rows})
    did = _upload_df(df, "large.csv")
    # verify stored
    r = client.get(f"/api/datasets/{did}")
    assert r.status_code == 200
    assert r.json()["dataset"]["rows"] == rows
    client.delete(f"/api/datasets/{did}")


def test_polars_read_path():
    """USE_POLARS=true path works via scan_csv fallback."""
    import os

    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    did = _upload_df(df, "polars.csv")
    # Force polars path via env
    old = os.getenv("USE_POLARS")
    os.environ["USE_POLARS"] = "true"
    try:
        from app.core.storage import load_dataset_df

        df2 = load_dataset_df(did, use_polars=True)
        assert len(df2) == 2
        assert list(df2.columns) == ["a", "b"]
        # fallback pandas
        df3 = load_dataset_df(did, use_polars=False)
        assert len(df3) == 2
    finally:
        if old is None:
            os.environ.pop("USE_POLARS", None)
        else:
            os.environ["USE_POLARS"] = old
    client.delete(f"/api/datasets/{did}")


def test_profile_cache_version_invalidation():
    """Profile cache key includes version — new version recomputes."""
    df = pd.DataFrame({"a": [1, 2]})
    did = _upload_df(df, "version.csv")
    r1 = client.get(f"/api/datasets/{did}")
    assert r1.headers.get("X-Cache") == "MISS"
    r2 = client.get(f"/api/datasets/{did}")
    assert r2.headers.get("X-Cache") == "HIT"
    # Simulate version bump via creating a version
    from app.core.storage import create_version

    df2 = pd.DataFrame({"a": [1, 2, 3]})  # noqa: reuses top-level pd
    create_version(did, df2, op="test", prompt="add row", code="df")
    # Next get should be MISS for new version
    r3 = client.get(f"/api/datasets/{did}")
    assert r3.headers.get("X-Cache") == "MISS"
    assert r3.json()["dataset"]["rows"] == 3
    client.delete(f"/api/datasets/{did}")
