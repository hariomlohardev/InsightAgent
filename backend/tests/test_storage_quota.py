import tempfile
from pathlib import Path
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app
from app.core import storage

client = TestClient(app)

def test_conversation_pagination_and_delete():
    df = pd.DataFrame({"A": [1,2]})
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmp:
        df.to_csv(tmp.name, index=False)
        tmp_path = Path(tmp.name)
    try:
        with open(tmp_path, "rb") as f:
            r = client.post("/api/datasets/upload", files={"file": ("test.csv", f, "text/csv")})
        dataset_id = r.json()["id"]
        
        # Create 3 conversations
        for i in range(3):
            r = client.post("/api/chat", json={"dataset_id": dataset_id, "query": f"show head {i}"})
            assert r.status_code == 200
        
        # List with pagination
        r = client.get(f"/api/chat/conversations?dataset_id={dataset_id}&limit=2&offset=0")
        assert r.status_code == 200
        assert len(r.json()) == 2
        
        r = client.get(f"/api/chat/conversations?dataset_id={dataset_id}&limit=2&offset=2")
        assert r.status_code == 200
        # Should have 1 left
        assert len(r.json()) == 1
        
        # Delete one
        conv_id = r.json()[0]["id"]
        r = client.delete(f"/api/chat/conversations/{conv_id}")
        assert r.status_code == 200
        
        # Verify deleted
        r = client.get(f"/api/chat/conversations/{conv_id}")
        assert r.status_code == 404
        
        # Cleanup
        client.delete(f"/api/datasets/{dataset_id}")
    finally:
        tmp_path.unlink(missing_ok=True)

def test_dataset_list_pagination():
    r = client.get("/api/datasets?limit=1&offset=0")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
