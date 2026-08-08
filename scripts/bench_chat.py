"""Bench chat groupby <2s."""

import time
import pandas as pd
import numpy as np
from pathlib import Path


def bench_chat(rows: int = 1_000_000):
    # Generate 1M sales-like df
    print(f"Generating {rows} rows for chat bench...")
    df = pd.DataFrame(
        {
            "Region": np.random.choice(["A", "B", "C", "D"], rows),
            "Sales": np.random.randn(rows) * 1000 + 5000,
            "Category": np.random.choice(["X", "Y", "Z"], rows),
        }
    )
    # Simulate chat groupby (what chat does for 'sales by region')
    start = time.time()
    res = df.groupby("Region")["Sales"].sum().reset_index()
    ms = (time.time() - start) * 1000
    print(f"Groupby Region sum {rows} rows: {ms:.0f}ms shape={res.shape} (target <2000ms)")
    # Also via duckdb
    try:
        import duckdb

        start2 = time.time()
        con = duckdb.connect()
        con.register("df", df)
        res2 = con.execute("SELECT Region, SUM(Sales) FROM df GROUP BY Region").fetchdf()
        ms2 = (time.time() - start2) * 1000
        print(f"DuckDB groupby {rows} rows: {ms2:.0f}ms shape={res2.shape}")
        return min(ms, ms2)
    except Exception as e:
        print(f"DuckDB not available: {e}")
        return ms


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1_000_000)
    args = ap.parse_args()
    bench_chat(args.rows)
    bench_chat(100_000)  # quick widget refresh <1s
