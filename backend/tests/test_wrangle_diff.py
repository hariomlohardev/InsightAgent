import pandas as pd
from app.core.wrangle import diff_dataframes, validate_clean_result

def test_diff_no_change():
    df = pd.DataFrame({"A": [1,2], "B": [3,4]})
    diff = diff_dataframes(df, df)
    assert diff["rows_before"] == 2
    assert diff["rows_after"] == 2
    assert diff["shape_changed"] is False
    assert diff["nulls_fixed"] == 0

def test_diff_remove_duplicates():
    df = pd.DataFrame({"A": [1,1,2], "B": [3,3,4]})
    df2 = df.drop_duplicates()
    diff = diff_dataframes(df, df2)
    assert diff["rows_before"] == 3
    assert diff["rows_after"] == 2
    assert diff["rows_removed"] == 1

def test_diff_fill_nulls():
    df = pd.DataFrame({"A": [1, None, 3]})
    df2 = df.fillna(df["A"].median())
    diff = diff_dataframes(df, df2)
    assert diff["nulls_before"] == 1
    assert diff["nulls_after"] == 0
    assert diff["nulls_fixed"] == 1

def test_diff_add_column():
    df = pd.DataFrame({"A": [1,2]})
    df2 = df.copy()
    df2["B"] = [3,4]
    diff = diff_dataframes(df, df2)
    assert "B" in diff["cols_added"]
    assert diff["cols_before"] == 1
    assert diff["cols_after"] == 2

def test_validate_ok():
    df = pd.DataFrame({"A": [1,2]})
    df2 = df.copy()
    assert validate_clean_result(df, df2)["valid"] is True

def test_validate_explosion():
    df = pd.DataFrame({"A": [1,2]})
    df2 = pd.DataFrame({"A": list(range(100))})  # 2 -> 100 rows, >10x
    res = validate_clean_result(df, df2)
    assert res["valid"] is False
    assert "exploded" in res["reason"].lower()

def test_validate_not_dataframe():
    df = pd.DataFrame({"A": [1,2]})
    assert validate_clean_result(df, None)["valid"] is False
