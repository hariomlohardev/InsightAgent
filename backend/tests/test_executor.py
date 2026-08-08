import pandas as pd
from app.agent.executor import execute_code

def test_executor_simple_groupby():
    df = pd.DataFrame({"Product": ["A","B","A"], "Sales":[100,200,150]})
    code = "result = df.groupby('Product')['Sales'].sum().reset_index()\nfig = px.bar(result, x='Product', y='Sales', title='Test')"
    res = execute_code(code, df)
    assert res["success"] is True
    assert res["result_json"] is not None
    assert res["chart_json"] is not None
    assert res["result_json"]["rows"] == 2

def test_executor_blocks_unsafe():
    df = pd.DataFrame({"A":[1,2]})
    code = "import os\nos.listdir('.')"
    res = execute_code(code, df)
    assert res["success"] is False
    assert "Security" in res["error"]

def test_executor_handles_error():
    df = pd.DataFrame({"A":[1,2]})
    code = "result = df['NonExistent'].sum()"
    res = execute_code(code, df)
    assert res["success"] is False

def test_executor_describe():
    df = pd.DataFrame({"A":[1,2,3], "B":["x","y","z"]})
    code = "result = df.describe(include='all').T.reset_index()"
    res = execute_code(code, df)
    assert res["success"] is True
    assert res["result_json"]["rows"] >= 1
