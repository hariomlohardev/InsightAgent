import pytest
from app.core.profiling import profile_dataframe
from app.agent.coder import fallback_coder
import pandas as pd

def test_no_import_in_generated_code():
    """Ensure no generated code contains 'import' (pd/px already in safe globals)."""
    df = pd.DataFrame({
        "Date": ["2024-01-01", "2024-02-01"],
        "Sales": [100, 200],
        "Product": ["A", "B"],
        "Region": ["North", "South"]
    })
    profile = profile_dataframe(df)
    queries = [
        "Show top 5 products by sales",
        "Monthly sales trend",
        "Correlation heatmap",
        "Distribution of Sales",
        "Average sales by category",
        "Show sales by region",
        "Describe dataset",
        "Pie share of sales by category",
        "Sales vs Quantity scatter",
        "Filter where Sales > 100",
        "SELECT * FROM df WHERE Sales > 100",
    ]
    for q in queries:
        result = fallback_coder(q, profile)
        code = result["code"]
        assert "import " not in code, f"Query '{q}' generated code with import: {code}"
        # Also ensure no __import__
        assert "__import__" not in code

def test_all_templates_deterministic():
    """Snapshot test: each pattern should generate code containing expected snippet."""
    df = pd.DataFrame({
        "Product": ["A", "B", "A"],
        "Sales": [100, 200, 150],
        "Quantity": [1, 2, 1],
        "Date": ["2024-01-01", "2024-01-02", "2024-01-03"]
    })
    profile = profile_dataframe(df)
    cases = [
        ("top 5 products by sales", "groupby"),
        ("monthly sales trend", "Grouper"),
        ("correlation", "corr"),
        ("distribution of sales", "histogram"),
        ("pie share", "pie"),
        ("sales vs quantity", "scatter"),
        ("average sales by product", "groupby"),
        ("describe dataset", "describe"),
        ("filter where Sales > 100", "query"),
        ("SELECT * FROM df", "duckdb.query"),
    ]
    for query, snippet in cases:
        result = fallback_coder(query, profile)
        assert snippet.lower() in result["code"].lower(), f"Query '{query}' missing '{snippet}': {result['code']}"
