import pandas as pd
from app.core.profiling import profile_dataframe, get_profile_summary_text

def test_profile_simple():
    df = pd.DataFrame({
        "Product": ["A", "B", "A"],
        "Sales": [100, 200, 150],
        "Date": ["2024-01-01", "2024-01-02", "2024-01-03"]
    })
    profile = profile_dataframe(df)
    assert profile["shape"]["rows"] == 3
    assert profile["shape"]["columns"] == 3
    assert "Product" in profile["column_names"]
    assert "Sales" in profile["numeric_columns"]
    assert profile["duplicates"] == 0
    assert len(profile["sample_rows"]) == 3

def test_profile_summary_text():
    df = pd.DataFrame({"A": [1,2], "B": ["x","y"]})
    profile = profile_dataframe(df)
    text = get_profile_summary_text(profile)
    assert "Dataset shape" in text
    assert "A" in text
