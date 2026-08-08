import pandas as pd
from app.core.profiling import profile_dataframe

def test_profile_empty_df():
    df = pd.DataFrame({"A": [], "B": []})
    profile = profile_dataframe(df)
    assert profile["shape"]["rows"] == 0
    assert profile["shape"]["columns"] == 2
    assert profile["sample_rows"] == []
    assert profile["describe"] == {} or isinstance(profile["describe"], dict)

def test_profile_no_rows_but_columns():
    df = pd.DataFrame(columns=["A", "B", "C"])
    profile = profile_dataframe(df)
    assert profile["shape"]["rows"] == 0
    assert len(profile["columns"]) == 3

def test_profile_all_nulls():
    df = pd.DataFrame({"A": [None, None], "B": [None, None]})
    profile = profile_dataframe(df)
    assert profile["columns"][0]["nulls"] == 2
    assert profile["sample_rows"] is not None

def test_profile_wide_file():
    # 25 columns, should limit describe to 20
    data = {f"col{i}": [1,2] for i in range(25)}
    df = pd.DataFrame(data)
    profile = profile_dataframe(df)
    assert profile["shape"]["columns"] == 25
    assert len(profile["describe"]) <= 20

def test_profile_date_inference():
    df = pd.DataFrame({"Date": ["2024-01-01", "2024-01-02"], "Sales": [100, 200]})
    profile = profile_dataframe(df)
    date_col = [c for c in profile["columns"] if c["name"] == "Date"][0]
    assert date_col.get("inferred_type") == "datetime"
    assert profile["inferred_roles"]["Date"] == "datetime"

def test_profile_no_date_inference_on_random():
    df = pd.DataFrame({"Product": ["A", "B"], "Sales": [100, 200]})
    profile = profile_dataframe(df)
    prod_col = [c for c in profile["columns"] if c["name"] == "Product"][0]
    assert prod_col.get("inferred_type") != "datetime"

def test_profile_inferred_roles():
    df = pd.DataFrame({"Sales": [100, 200], "Product": ["A", "B"]})
    profile = profile_dataframe(df)
    assert profile["inferred_roles"]["Sales"] == "measure"
    assert profile["inferred_roles"]["Product"] == "dimension"
