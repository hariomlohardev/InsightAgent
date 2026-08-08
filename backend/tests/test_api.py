import tempfile
from pathlib import Path
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "InsightAgent" in r.json()["name"]


def test_upload_and_chat():
    # Create temp csv
    df = pd.DataFrame({"Product": ["A", "B", "A"], "Sales": [100, 200, 150], "Quantity": [1, 2, 1]})
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", newline="") as tmp:
        df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)

    try:
        # Upload
        with open(tmp_path, "rb") as f:
            r = client.post("/api/datasets/upload", files={"file": ("test.csv", f, "text/csv")})
        assert r.status_code == 200, r.text
        dataset_id = r.json()["id"]
        assert dataset_id

        # List
        r = client.get("/api/datasets")
        assert r.status_code == 200
        assert any(d["id"] == dataset_id for d in r.json())

        # Get details
        r = client.get(f"/api/datasets/{dataset_id}")
        assert r.status_code == 200
        assert "profile" in r.json()

        # Chat - top products
        r = client.post(
            "/api/chat", json={"dataset_id": dataset_id, "query": "Show top 5 products by sales"}
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["success"] is True
        assert j["result"] is not None
        assert "insight" in j
        assert j["conversation_id"]

        # Chat - trend (fallback)
        r = client.post(
            "/api/chat", json={"dataset_id": dataset_id, "query": "average sales by product"}
        )
        assert r.status_code == 200
        assert r.json()["success"] is True

        # Preview
        r = client.get(f"/api/datasets/{dataset_id}/preview?rows=2")
        assert r.status_code == 200
        assert "data" in r.json()

        # Conversations
        r = client.get("/api/chat/conversations", params={"dataset_id": dataset_id})
        assert r.status_code == 200
        assert len(r.json()) >= 1

        # Delete
        r = client.delete(f"/api/datasets/{dataset_id}")
        assert r.status_code == 200

        # Should be 404 after delete
        r = client.get(f"/api/datasets/{dataset_id}")
        assert r.status_code == 404

    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_upload_invalid():
    r = client.post("/api/datasets/upload", files={"file": ("test.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_chat_invalid_dataset():
    r = client.post("/api/chat", json={"dataset_id": "nonexistent", "query": "hello"})
    assert r.status_code == 404


def test_chat_empty_query():
    # Need a valid dataset first
    df = pd.DataFrame({"A": [1, 2]})
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            r = client.post("/api/datasets/upload", files={"file": ("test2.csv", f, "text/csv")})
        dataset_id = r.json()["id"]
        r = client.post("/api/chat", json={"dataset_id": dataset_id, "query": "   "})
        assert r.status_code == 400
        # cleanup
        client.delete(f"/api/datasets/{dataset_id}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
