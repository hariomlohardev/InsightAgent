import tempfile
from pathlib import Path
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def _upload_dirty():
    # Create dirty df: duplicates, nulls, whitespace - ensure at least 1 clear duplicate
    df = pd.DataFrame({
        "Product": ["A", "A", "B", "B"],
        "Sales": [100, 100, 100, 200],
        "Price": [10, 10, 20, 20],
        "Date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-03"]
    })
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w")
    df.to_csv(tmp.name, index=False)
    tmp_path = Path(tmp.name)
    with open(tmp_path, "rb") as f:
        r = client.post("/api/datasets/upload", files={"file": ("dirty.csv", f, "text/csv")})
    tmp_path.unlink(missing_ok=True)
    assert r.status_code == 200
    return r.json()["id"]

def test_preview_clean_remove_duplicates():
    dataset_id = _upload_dirty()
    try:
        r = client.post(f"/api/datasets/{dataset_id}/preview-clean", json={"query": "remove duplicates"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "drop_duplicates" in data["code"]
        assert data["diff"] is not None
        assert data["diff"]["rows_removed"] >= 1
        assert data["preview"] is not None
    finally:
        client.delete(f"/api/datasets/{dataset_id}")

def test_preview_fill_nulls():
    dataset_id = _upload_dirty()
    try:
        r = client.post(f"/api/datasets/{dataset_id}/preview-clean", json={"query": "fill missing Sales with median"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "fillna" in data["code"]
        assert "Sales" in data["code"]
    finally:
        client.delete(f"/api/datasets/{dataset_id}")

def test_apply_and_version():
    dataset_id = _upload_dirty()
    try:
        # Preview first
        r = client.post(f"/api/datasets/{dataset_id}/preview-clean", json={"query": "remove duplicates"})
        preview = r.json()
        code = preview["code"]
        # Apply
        r = client.post(f"/api/datasets/{dataset_id}/apply-clean", json={"query": "remove duplicates", "code": code})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "new_version" in data
        assert data["new_version"] == 1
        # Check versions
        r = client.get(f"/api/datasets/{dataset_id}/versions")
        assert r.status_code == 200
        versions = r.json()["versions"]
        assert len(versions) == 2  # v0 + v1
        assert any(v["version"] == 1 for v in versions)
        # Check that rows decreased
        r = client.get(f"/api/datasets/{dataset_id}")
        assert r.json()["dataset"]["rows"] == 3  # was 4, now 3 after dedup
    finally:
        client.delete(f"/api/datasets/{dataset_id}")

def test_revert():
    dataset_id = _upload_dirty()
    try:
        # Get original rows
        r = client.get(f"/api/datasets/{dataset_id}")
        orig_rows = r.json()["dataset"]["rows"]
        # Apply
        r = client.post(f"/api/datasets/{dataset_id}/apply-clean", json={"query": "remove duplicates"})
        assert r.json()["success"] is True
        # Revert to 0
        r = client.post(f"/api/datasets/{dataset_id}/revert", json={"version": 0})
        assert r.status_code == 200
        assert r.json()["status"] == "reverted"
        # Check rows back to orig
        r = client.get(f"/api/datasets/{dataset_id}")
        assert r.json()["dataset"]["rows"] == orig_rows
    finally:
        client.delete(f"/api/datasets/{dataset_id}")

def test_chat_cleaning_intent():
    dataset_id = _upload_dirty()
    try:
        r = client.post("/api/chat", json={"dataset_id": dataset_id, "query": "remove duplicates"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["intent"]["intent"] == "cleaning"
        assert "drop_duplicates" in data["generated_code"]
        assert data.get("diff") is not None or data["result"] is not None
    finally:
        client.delete(f"/api/datasets/{dataset_id}")

def test_wrangle_invalid_version():
    dataset_id = _upload_dirty()
    try:
        r = client.post(f"/api/datasets/{dataset_id}/revert", json={"version": 99})
        assert r.status_code == 404
    finally:
        client.delete(f"/api/datasets/{dataset_id}")
