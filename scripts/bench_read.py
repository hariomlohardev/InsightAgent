"""Bench read — compare read_csv vs scan_csv vs parquet (BF-01)."""
import time
import json
import argparse
from pathlib import Path
import pandas as pd

def bench_read(csv_path: Path, engines=("polars","parquet","pandas")):
    import os
    results = {}
    df = None
    # polars scan
    if "polars" in engines:
        try:
            import polars as pl
            t0 = time.time()
            df_pl = pl.scan_csv(str(csv_path), infer_schema_length=1000).collect()
            df = df_pl.to_pandas()
            ms = (time.time()-t0)*1000
            results["polars_scan"] = {"read_ms": round(ms,1), "rows": df.shape[0], "cols": df.shape[1]}
            # also try streaming if available
            try:
                t0 = time.time()
                df_pl2 = pl.scan_csv(str(csv_path), infer_schema_length=1000).collect(streaming=True)
                ms2 = (time.time()-t0)*1000
                results["polars_streaming"] = {"read_ms": round(ms2,1), "rows": df_pl2.shape[0]}
            except Exception as e:
                results["polars_streaming"] = {"error": str(e)[:120]}
        except Exception as e:
            results["polars_scan"] = {"error": str(e)[:200]}
    # pandas
    if "pandas" in engines:
        t0 = time.time()
        df_pd = pd.read_csv(csv_path)
        ms = (time.time()-t0)*1000
        results["pandas"] = {"read_ms": round(ms,1), "rows": df_pd.shape[0], "cols": df_pd.shape[1]}
        # chunksize
        t0 = time.time()
        chunks = []
        for ch in pd.read_csv(csv_path, chunksize=100000):
            chunks.append(ch)
        df_ch = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        ms2 = (time.time()-t0)*1000
        results["pandas_chunked"] = {"read_ms": round(ms2,1), "rows": df_ch.shape[0]}
        df = df_pd
    # parquet (write then read if df available)
    if "parquet" in engines and df is not None:
        pq = Path(str(csv_path).replace(".csv",".parquet"))
        try:
            t0 = time.time()
            df.to_parquet(pq, index=False)
            w_ms = (time.time()-t0)*1000
            t0 = time.time()
            df_r = pd.read_parquet(pq)
            r_ms = (time.time()-t0)*1000
            results["parquet"] = {"write_ms": round(w_ms,1), "read_ms": round(r_ms,1), "rows": df_r.shape[0]}
            # polars parquet read
            try:
                import polars as pl
                t0 = time.time()
                df_pl = pl.scan_parquet(str(pq)).collect()
                ms = (time.time()-t0)*1000
                results["parquet_polars"] = {"read_ms": round(ms,1), "rows": df_pl.shape[0]}
            except Exception as e:
                results["parquet_polars"] = {"error": str(e)[:120]}
        except Exception as e:
            results["parquet"] = {"error": str(e)[:200]}
    return results

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Bench read engines")
    ap.add_argument("--rows", type=int, default=1_000_000)
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--engines", type=str, default="polars,parquet,pandas", help="comma list")
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--csv", type=str, default=None, help="existing csv path")
    args = ap.parse_args()
    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_path = Path(f"/tmp/bench_{args.rows}.csv")
        if not csv_path.exists() or csv_path.stat().st_size < 1000:
            # generate via bench_profile helper
            import numpy as np
            print(f"Generating {args.rows} rows -> {csv_path}")
            chunk = 500_000
            header = False
            for start in range(0, args.rows, chunk):
                end = min(start+chunk, args.rows)
                n = end-start
                df = pd.DataFrame({
                    "id": np.arange(start,end),
                    "value": np.random.randn(n)*100,
                    "category": np.random.choice(["A","B","C","D"], n),
                    "date": pd.date_range("2020-01-01", periods=n, freq="h").astype(str)[:n],
                    "flag": np.random.choice([True, False], n),
                })
                if args.cols <5:
                    df = df.iloc[:, :args.cols]
                df.to_csv(csv_path, mode="w" if not header else "a", header=not header, index=False)
                header=True
    engines = [e.strip() for e in args.engines.split(",")]
    res = bench_read(csv_path, engines=engines)
    res["csv"] = str(csv_path)
    res["rows"] = args.rows
    if args.json:
        s = json.dumps(res, indent=2)
        if args.out:
            Path(args.out).write_text(s)
            print(s)
            print(f"Wrote {args.out}")
        else:
            print(s)
    else:
        print(f"Bench read {csv_path.name}:")
        for k,v in res.items():
            print(f"  {k}: {v}")
