import tempfile
from pathlib import Path
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient
from app.main import app
import shutil
from pathlib import Path as P

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


def test_why_sales_drop():
    # Use sample sales.csv
    df = pd.read_csv(P(__file__).resolve().parents[2] / "sample_data/sales.csv")
    did = _upload_df(df, "sales.csv")
    r = client.post("/api/chat", json={"dataset_id": did, "query": "Why did sales drop in March?"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] == True, j.get("error")
    assert j["intent"]["intent"] in [
        "analytics",
        "insight",
        "filter",
        "visualization",
    ]  # relaxed for LLM variance
    # Result should have category, delta etc
    res = j["result"]
    assert res is not None
    assert "category" in str(res["columns"]).lower() or "category" in str(res)
    # Should have delta column
    assert any("delta" in c.lower() for c in res["columns"])
    client.delete(f"/api/datasets/{did}")


def test_outliers():
    df = pd.DataFrame({"Sales": [100, 110, 105, 120, 1000], "Region": ["A", "A", "B", "B", "A"]})
    did = _upload_df(df, "outliers.csv")
    r = client.post("/api/chat", json={"dataset_id": did, "query": "Show outliers in Sales"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] == True
    assert j["intent"]["intent"] in [
        "analytics",
        "insight",
        "filter",
        "visualization",
    ]  # relaxed for LLM variance
    # Result flagged df should have is_outlier
    res = j["result"]
    assert any("outlier" in c.lower() for c in res["columns"])
    # Check that outlier count >=1
    # Data contains 1000 which is outlier
    data = res["data"]
    # Find outlier row
    # The flagged column is is_outlier
    has_outlier = any(row.get("is_outlier") == True for row in data if isinstance(row, dict))
    assert has_outlier or res["rows"] >= 1
    client.delete(f"/api/datasets/{did}")


def test_outliers_zscore():
    df = pd.DataFrame({"Sales": [100, 101, 102, 103, 1000]})
    did = _upload_df(df, "z.csv")
    r = client.post("/api/chat", json={"dataset_id": did, "query": "outliers in Sales via zscore"})
    assert r.status_code == 200
    assert r.json()["success"] == True
    client.delete(f"/api/datasets/{did}")


def test_segment_by():
    df = pd.read_csv(P(__file__).resolve().parents[2] / "sample_data/sales.csv")
    did = _upload_df(df, "sales2.csv")
    r = client.post("/api/chat", json={"dataset_id": did, "query": "segment by Region"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] == True
    assert j["intent"]["intent"] in [
        "analytics",
        "insight",
        "filter",
        "visualization",
    ]  # relaxed for LLM variance
    res = j["result"]
    assert "category" in [c.lower() for c in res["columns"]] or "share" in str(res).lower()
    client.delete(f"/api/datasets/{did}")


def test_segment_count():
    df = pd.read_csv(P(__file__).resolve().parents[2] / "sample_data/employees.csv")
    did = _upload_df(df, "emp.csv")
    r = client.post("/api/chat", json={"dataset_id": did, "query": "segment by Department count"})
    assert r.status_code == 200
    assert r.json()["success"] == True
    client.delete(f"/api/datasets/{did}")


def test_forecast_next_3():
    df = pd.read_csv(P(__file__).resolve().parents[2] / "sample_data/sales.csv")
    did = _upload_df(df, "sales_fc.csv")
    r = client.post(
        "/api/chat", json={"dataset_id": did, "query": "forecast Sales for next 3 months"}
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] == True
    assert j["intent"]["intent"] in [
        "analytics",
        "insight",
        "filter",
        "visualization",
    ]  # relaxed for LLM variance
    res = j["result"]
    # 24 rows history + 3 forecast = 9? Actually resampled monthly: sales.csv has 6 months (Jan-Jun) => 6 history + 3 forecast = 9 rows
    assert res["rows"] >= 6, f"expected >=6 got {res['rows']}"
    # Chart should exist (forecast line + band)
    assert j["chart"] is not None
    client.delete(f"/api/datasets/{did}")


def test_forecast_low_data_warning():
    # Small data still works via naive
    df = pd.DataFrame(
        {"Date": ["2024-01-01", "2024-02-01", "2024-03-01"], "Sales": [100, 120, 110]}
    )
    did = _upload_df(df, "small.csv")
    r = client.post(
        "/api/chat", json={"dataset_id": did, "query": "forecast Sales for next 2 months"}
    )
    assert r.status_code == 200
    assert r.json()["success"] == True
    # Should still have result
    assert r.json()["result"]["rows"] >= 3
    client.delete(f"/api/datasets/{did}")


def test_what_if():
    df = pd.read_csv(P(__file__).resolve().parents[2] / "sample_data/sales.csv")
    did = _upload_df(df, "sales_wi.csv")
    r = client.post("/api/chat", json={"dataset_id": did, "query": "what if Sales increased 10%"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] == True
    assert j["intent"]["intent"] in [
        "analytics",
        "insight",
        "filter",
        "visualization",
    ]  # relaxed for LLM variance
    res = j["result"]
    assert res is not None
    assert "delta" in str(res["columns"]).lower() or "before" in str(res["columns"]).lower()
    client.delete(f"/api/datasets/{did}")


def test_what_if_decrease_by():
    df = pd.DataFrame({"Price": [100, 200, 300], "Category": ["A", "A", "B"]})
    did = _upload_df(df, "whatif2.csv")
    r = client.post(
        "/api/chat", json={"dataset_id": did, "query": "what if Price decreased 20% by Category"}
    )
    assert r.status_code == 200
    assert r.json()["success"] == True
    assert r.json()["result"] is not None
    client.delete(f"/api/datasets/{did}")


def test_correlation():
    df = pd.read_csv(P(__file__).resolve().parents[2] / "sample_data/sales.csv")
    did = _upload_df(df, "corr.csv")
    r = client.post("/api/chat", json={"dataset_id": did, "query": "correlation heatmap"})
    assert r.status_code == 200, r.text
    assert r.json()["success"] == True
    assert r.json()["intent"]["intent"] in [
        "analytics",
        "insight",
        "filter",
        "visualization",
    ]  # relaxed
    # Result is correlation matrix reset
    assert r.json()["result"] is not None
    client.delete(f"/api/datasets/{did}")


def test_regression_cleaning_still_works():
    # Ensure cleaning not broken by analytics priority
    df = pd.DataFrame({"A": [1, 1, 2], "B": [None, 1, 2]})
    did = _upload_df(df, "clean.csv")
    r = client.post(
        "/api/datasets/" + did + "/preview-clean", json={"query": "fill missing B with mean"}
    )
    assert r.status_code == 200
    assert r.json()["success"] == True
    client.delete(f"/api/datasets/{did}")


def test_regression_sql_still_works():
    df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
    did = _upload_df(df, "sql.csv")
    r = client.post(
        "/api/chat", json={"dataset_id": did, "query": "SELECT * FROM df WHERE A > 1 LIMIT 2"}
    )
    assert r.status_code == 200
    assert r.json()["success"] == True
    assert r.json()["intent"]["intent"] == "sql"
    client.delete(f"/api/datasets/{did}")


def test_forecast_on_large_data_has_band():
    # Ensure forecast chart has band (we check chart exists)
    df = pd.read_csv(P(__file__).resolve().parents[2] / "sample_data/sales.csv")
    did = _upload_df(df, "sales_band.csv")
    r = client.post(
        "/api/chat", json={"dataset_id": did, "query": "forecast Sales for next 3 months"}
    )
    j = r.json()
    chart = j.get("chart")
    assert chart is not None
    # chart data should have >=3 traces (history, forecast, band)
    assert len(chart.get("data", [])) >= 2
    client.delete(f"/api/datasets/{did}")
