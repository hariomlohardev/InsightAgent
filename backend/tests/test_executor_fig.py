import pandas as pd
import numpy as np
from app.agent.executor import execute_code

def test_fig_serializable_with_ndarray():
    df = pd.DataFrame({"A": ["x", "y"], "B": [1, 2]})
    code = "result = df.groupby('A')['B'].sum().reset_index()\nfig = px.bar(result, x='A', y='B', title='Test')"
    # px is in safe globals, but we need to ensure fig conversion handles ndarray
    res = execute_code(code, df)
    assert res["success"] is True
    assert res["chart_json"] is not None
    # Ensure no ndarray in chart_json
    import json
    try:
        json.dumps(res["chart_json"])
    except TypeError as e:
        pytest.fail(f"chart_json not serializable: {e}")
    # Check that chart has data
    assert "data" in res["chart_json"]

def test_fig_with_numpy_types():
    df = pd.DataFrame({"A": [1,2,3], "B": [np.int64(10), np.float64(20.5), np.int64(30)]})
    code = "result = df\nfig = px.bar(result, x='A', y='B')"
    res = execute_code(code, df)
    assert res["success"] is True
    # Should be serializable
    import json
    json.dumps(res["result_json"])
    json.dumps(res["chart_json"])

def test_result_truncation():
    df = pd.DataFrame({"A": range(200), "B": range(200)})
    code = "result = df"
    res = execute_code(code, df)
    assert res["success"] is True
    assert res["result_json"]["rows"] == 200
    assert res["result_json"]["truncated"] is True
    assert len(res["result_json"]["data"]) == 100  # truncated to 100
