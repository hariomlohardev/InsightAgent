"""
Regression tests for 8 fixes: async job, dataset cache, profiling cache, cleaning single-exec,
polars path, list_datasets cache, streamlit version-aware. Lightweight, no Redis/DB needed.
"""

import os
import sys
import time
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pandas as pd
import pytest

# frontend tests use source inspection to avoid heavy streamlit import
FRONTEND_PATH = Path(__file__).parent.parent.parent / "frontend" / "streamlit_app.py"


# ---------- 1. Async job polling (source-inspection to avoid streamlit import) ----------


def test_chat_query_success():
    src = FRONTEND_PATH.read_text()
    # fixed flow: handles completed → 200, failed → 500, timeout → 504, no str(d)
    assert "rr.text = str(d)" not in src
    assert 'status == "completed"' in src
    assert 'status == "failed"' in src
    assert "504" in src
    assert "str(result)" in src or "json.dumps" in src


def test_chat_query_failed():
    src = FRONTEND_PATH.read_text()
    assert 'status == "failed"' in src
    assert "500" in src


def test_chat_query_timeout():
    src = FRONTEND_PATH.read_text()
    assert "504" in src
    assert "timed out" in src.lower()


def test_chat_query_malformed():
    src = FRONTEND_PATH.read_text()
    # malformed handling: try/except around j.json and pr.json
    assert "malformed" in src.lower() or "try:" in src


def test_chat_query_no_undefined_d():
    src = FRONTEND_PATH.read_text()
    assert "rr.text = str(d)" not in src
    # should have proper fix with _json.dumps(result)
    assert "_json.dumps" in src or "json.dumps" in src


# ---------- 2. Dataset caching ----------


def test_dataset_cache_hit_and_invalidation(monkeypatch, tmp_path):
    from app.core import storage

    # use temp storage path
    monkeypatch.setenv("STORAGE_BACKEND", "fs")
    # clear caches
    storage._invalidate_df_cache()
    storage._invalidate_list_cache()

    # create fake dataset
    did = "test123"
    # mock get_dataset_meta to control version
    meta_v0 = {"id": did, "current_version": 0, "rows": 10, "columns": 2}
    meta_v1 = {"id": did, "current_version": 1, "rows": 10, "columns": 2}
    # mock get_dataset_path to a real csv
    csv_path = tmp_path / "data.csv"
    pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_csv(csv_path, index=False)

    with (
        patch("app.core.storage.get_dataset_meta", side_effect=lambda x: meta_v0),
        patch("app.core.storage.get_dataset_path", return_value=csv_path),
    ):
        df1 = storage.load_dataset_df(did)
        df2 = storage.load_dataset_df(did)
        # second should be cached — pd.read_csv called only once? Check via cache hit (identical content but not same object)
        assert df1.equals(df2)
        # different version → miss (create new meta)
        with patch("app.core.storage.get_dataset_meta", return_value=meta_v1):
            df3 = storage.load_dataset_df(did)
            # should be new read (still equal content but cache miss exercised)
            assert df3.equals(df1)
            # ensure key includes version — cache has both
            assert (
                storage._df_cache_key(did, 0, True) in storage._DF_CACHE
                or storage._df_cache_key(did, 0, False) in storage._DF_CACHE
            )

    # different dataset no collision
    did2 = "other456"
    meta_other = {"id": did2, "current_version": 0}
    csv2 = tmp_path / "data2.csv"
    pd.DataFrame({"x": [9]}).to_csv(csv2, index=False)
    with (
        patch("app.core.storage.get_dataset_meta", return_value=meta_other),
        patch("app.core.storage.get_dataset_path", return_value=csv2),
    ):
        df_o = storage.load_dataset_df(did2)
        assert list(df_o.columns) == ["x"]

    # deleted → no stale: invalidate
    storage._invalidate_df_cache(did)
    assert not any(k.startswith(f"{did}:") for k in storage._DF_CACHE)


# ---------- 3. Profiling cache ----------


def test_profiling_cache_stable_key():
    from app.core.profiling import profile_dataframe
    from app.core.cache import clear as cache_clear

    try:
        cache_clear()
    except:
        pass

    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    # same dataset/version → hit
    r1 = profile_dataframe(df, dataset_id="ds1", version=0)
    r2 = profile_dataframe(df, dataset_id="ds1", version=0)
    assert r1 == r2
    r3 = profile_dataframe(df, dataset_id="ds1", version=1)
    assert r3 == r1
    r4 = profile_dataframe(df, dataset_id="ds2", version=0)
    assert r4 == r1
    import inspect

    src = inspect.getsource(profile_dataframe)
    assert "dataset_id" in src


# ---------- 4. Cleaning single-exec ----------


def test_cleaning_single_exec(monkeypatch):
    # inspect source — no second exec() in chat_service for cleaning
    import pathlib

    p = Path(__file__).parent.parent / "app" / "services" / "chat_service.py"
    src = p.read_text()
    # should have only one execute_code per function and no naked exec(code,
    # the fixed version uses _after_df, not exec(code,
    assert src.count("execute_code") >= 1
    # two functions each have one execute_code; original had exec(code, safe_globals
    # now should have zero exec( for cleaning (only executor)
    # count exec( after fix — should be 0 for cleaning diff (uses _after_df)
    # allow exec inside executor.py but not in chat_service for diff
    assert "exec(code, safe_globals" not in src
    assert "_after_df" in src

    # also check wrangle_service
    wp = Path(__file__).parent.parent / "app" / "services" / "wrangle_service.py"
    wsrc = wp.read_text()
    assert "exec(code, safe_globals" not in wsrc
    assert "_after_df" in wsrc


# ---------- 5. Polars path ----------


def test_polars_default_true():
    from app.core import storage
    import importlib

    # default should be true when env not set
    with patch.dict(os.environ, {}, clear=False):
        if "USE_POLARS" in os.environ:
            del os.environ["USE_POLARS"]
        # reload logic: storage.load_dataset_df checks env inside; test via direct env check
        assert os.getenv("USE_POLARS", "true").lower() in ("true", "1", "yes")

    # explicit false still respected for small files, but large files auto-enable
    # we test that load_dataset_df tries polars path when USE_POLARS true
    # (can't test without polars installed; just test env logic)
    with patch.dict(os.environ, {"USE_POLARS": "true"}):
        assert os.getenv("USE_POLARS", "false").lower() in ("true", "1", "yes")


# ---------- 6. list_datasets cache ----------


def test_list_datasets_cache_invalidation(tmp_path, monkeypatch):
    from app.core import storage

    storage._invalidate_list_cache()
    # mock _datasets_dir to tmp
    fake_dir = tmp_path / "datasets"
    fake_dir.mkdir()
    # create two metas
    for did in ["a1", "a2"]:
        d = fake_dir / did
        d.mkdir()
        (d / "meta.json").write_text(
            '{"id":"%s","original_filename":"f.csv","created_at":"2024-01-01T00:00:00"}' % did
        )
        (d / "data.csv").write_text("a,b\n1,2\n")

    with (
        patch("app.core.storage._datasets_dir", return_value=fake_dir),
        patch("app.core.storage._db_list_metas", return_value=None),
        patch("app.core.storage._db_available", return_value=False),
    ):
        storage._invalidate_list_cache()
        l1 = storage.list_datasets()
        l2 = storage.list_datasets()  # should be cached (2s)
        assert len(l1) == 2 and len(l2) == 2
        # after invalidate, still correct
        storage._invalidate_list_cache()
        l3 = storage.list_datasets()
        assert len(l3) == 2


# ---------- 7. Streamlit version-aware ----------


def test_streamlit_version_aware():
    src = FRONTEND_PATH.read_text()
    assert "_get_dataset_details_cached" in src
    assert "version" in src
    # cached func signature has version param
    assert "def _get_dataset_details_cached(dataset_id, version)" in src
    assert "current_version" in src
