import pandas as pd
from app.core.profiling import profile_dataframe
from app.agent.coder import fallback_coder


def make_profile():
    df = pd.DataFrame(
        {
            "Product": ["A", "B", "A"],
            "Sales": [100, 200, None],
            "Price": [10, 20, 30],
            "Date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "Category": ["X", "X", "Y"],
        }
    )
    return profile_dataframe(df)


def test_remove_duplicates():
    profile = make_profile()
    res = fallback_coder("remove duplicates", profile)
    assert "drop_duplicates" in res["code"]
    assert "result" in res["code"]


def test_fill_missing_median():
    profile = make_profile()
    res = fallback_coder("fill missing Sales with median", profile)
    assert "fillna" in res["code"]
    assert "Sales" in res["code"]
    assert "median" in res["code"].lower()


def test_fill_missing_mean():
    profile = make_profile()
    res = fallback_coder("fill missing Price with mean", profile)
    assert "fillna" in res["code"]
    assert "Price" in res["code"]


def test_drop_column():
    profile = make_profile()
    res = fallback_coder("drop column Price", profile)
    assert "drop" in res["code"]
    assert "Price" in res["code"]


def test_drop_rows_null():
    profile = make_profile()
    res = fallback_coder("drop rows where Sales is null", profile)
    assert "dropna" in res["code"]


def test_rename():
    profile = make_profile()
    res = fallback_coder("rename Product to Item", profile)
    assert "rename" in res["code"]
    assert "Product" in res["code"]
    assert "Item" in res["code"]


def test_convert_datetime():
    profile = make_profile()
    res = fallback_coder("convert Date to datetime", profile)
    assert "to_datetime" in res["code"]
    assert "Date" in res["code"]


def test_trim_whitespace():
    profile = make_profile()
    res = fallback_coder("trim whitespace in Product", profile)
    assert "str.strip" in res["code"]
    assert "Product" in res["code"]


def test_standardize_lower():
    profile = make_profile()
    res = fallback_coder("standardize Product to lower case", profile)
    assert "str.lower" in res["code"]


def test_split():
    profile = make_profile()
    res = fallback_coder("split Product by space", profile)
    assert "str.split" in res["code"]


def test_outliers():
    profile = make_profile()
    res = fallback_coder("remove outliers in Sales", profile)
    assert "mean" in res["code"] and "std" in res["code"]


def test_generic_clean():
    profile = make_profile()
    res = fallback_coder("clean my data", profile)
    assert "dropna" in res["code"] or "drop_duplicates" in res["code"]
