"""Bench profile — 1M/10M CSV <2s via polars scan_csv. BF-01 adds --json --per-col."""
import time
import argparse
import json
import os
from pathlib import Path
import pandas as pd
import numpy as np

def gen_csv(path: Path, rows: int, cols: int = 5):
    print(f"Generating {rows} rows x {cols} cols -> {path} ...")
    chunk = 500_000
    header_written = False
    for start in range(0, rows, chunk):
        end = min(start + chunk, rows)
        n = end - start
        df = pd.DataFrame({
            "id": np.arange(start, end),
            "value": np.random.randn(n) * 100,
            "category": np.random.choice(["A","B","C","D"], n),
            "date": pd.date_range("2020-01-01", periods=n, freq="h").astype(str)[:n],
            "flag": np.random.choice([True, False], n),
        })
        if cols < 5:
            df = df.iloc[:, :cols]
        df.to_csv(path, mode="w" if not header_written else "a", header=not header_written, index=False)
        header_written = True
        print(f"  {end}/{rows}")

def load_dataset_df_csv(csv_path: Path, use_polars: bool = False):
    import pandas as pd
    if use_polars:
        try:
            import polars as pl
            try:
                # BF-01: try streaming, fallback to plain collect
                return pl.scan_csv(str(csv_path), infer_schema_length=1000).collect().to_pandas()
            except Exception:
                return pl.read_csv(str(csv_path)).to_pandas()
        except ImportError:
            pass
    fsize = csv_path.stat().st_size
    if fsize > 50*1024*1024:
        chunks = []
        for chunk in pd.read_csv(csv_path, chunksize=100000):
            chunks.append(chunk)
            if sum(len(c) for c in chunks) > 10_000_000:
                break
        return pd.concat(chunks, ignore_index=True)
    return pd.read_csv(csv_path)

def _time_per_col(df: pd.DataFrame):
    """Return per-col timing for B1 diagnostics: null_ms, nunique_ms, value_counts_ms."""
    per_col = []
    for col in df.columns:
        t0 = time.time()
        try:
            _ = int(df[col].isna().sum())
        except Exception:
            pass
        null_ms = (time.time() - t0) * 1000
        t0 = time.time()
        try:
            _ = int(df[col].nunique(dropna=True))
        except Exception:
            pass
        nunique_ms = (time.time() - t0) * 1000
        t0 = time.time()
        try:
            if df[col].dtype == object:
                _ = df[col].value_counts(dropna=True).head(5).to_dict()
        except Exception:
            pass
        vc_ms = (time.time() - t0) * 1000
        per_col.append({
            "name": str(col),
            "null_ms": round(null_ms, 2),
            "nunique_ms": round(nunique_ms, 2),
            "value_counts_ms": round(vc_ms, 2),
        })
    return per_col

def bench_profile(csv_path: Path, use_polars: bool, per_col: bool = False):
    import os
    orig = os.getenv("USE_POLARS")
    os.environ["USE_POLARS"] = "true" if use_polars else "false"
    # BF-01: also support DEBUG_PROFILE for breakdown
    debug_before = os.getenv("DEBUG_PROFILE")
    if per_col:
        os.environ["DEBUG_PROFILE"] = "1"
    try:
        t0 = time.time()
        df = load_dataset_df_csv(csv_path, use_polars=use_polars)
        load_ms = (time.time() - t0) * 1000
        # per-col diagnostics on the loaded df (before profile)
        per_col_data = _time_per_col(df) if per_col else []
        # time profile
        from app.core.profiling import profile_dataframe
        # force no cache for bench
        t1 = time.time()
        prof = profile_dataframe(df, dataset_id="bench", version=0, use_cache=False)
        prof_ms = (time.time() - t1) * 1000
        # time duplicated separately if needed
        dup_ms = 0
        if per_col:
            t2 = time.time()
            try:
                _ = int(df.duplicated().sum())
            except Exception:
                pass
            dup_ms = (time.time() - t2) * 1000
            # time describe
            t3 = time.time()
            try:
                _ = df.describe(include="all").fillna("").to_dict()
            except Exception:
                pass
            describe_ms = (time.time() - t3) * 1000
        else:
            describe_ms = 0
        total = load_ms + prof_ms
        engine = "polars" if use_polars else "pandas"
        result = {
            "rows": int(df.shape[0]),
            "cols": int(df.shape[1]),
            "engine": engine,
            "use_polars": use_polars,
            "read_ms": round(load_ms, 1),
            "profile_ms": round(prof_ms, 1),
            "total_ms": round(total, 1),
            "column_names": [str(c) for c in df.columns.tolist()],
        }
        if per_col:
            result["per_col"] = per_col_data
            result["duplicated_ms"] = round(dup_ms, 1)
            result["describe_ms"] = round(describe_ms, 1)
        return result
    finally:
        if orig is None:
            os.environ.pop("USE_POLARS", None)
        else:
            os.environ["USE_POLARS"] = orig
        if per_col:
            if debug_before is None:
                os.environ.pop("DEBUG_PROFILE", None)
            else:
                os.environ["DEBUG_PROFILE"] = debug_before

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Bench profile 1M/10M")
    ap.add_argument("--rows", type=int, default=1_000_000, help="1M or 10M")
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--no-polars", action="store_true", help="skip polars run")
    ap.add_argument("--json", action="store_true", help="output machine-readable JSON to stdout")
    ap.add_argument("--per-col", action="store_true", help="include per-col breakdown for BF-01 flame")
    ap.add_argument("--quiet", action="store_true", help="suppress human logs when --json")
    ap.add_argument("--out", type=str, default=None, help="write JSON to file instead of stdout")
    args = ap.parse_args()
    tmp = Path(f"/tmp/bench_{args.rows}.csv")
    if not tmp.exists() or tmp.stat().st_size < 1000:
        gen_csv(tmp, args.rows, args.cols)
    results = []
    # polars
    if not args.no_polars:
        r = bench_profile(tmp, use_polars=True, per_col=args.per_col)
        results.append(r)
        if not args.json and not args.quiet:
            print(f"Load {tmp.name} use_polars=True: {r['read_ms']:.0f}ms shape=({r['rows']}, {r['cols']})")
            print(f"Profile use_polars=True: {r['profile_ms']:.0f}ms cols={r['cols']}")
            print(f"Total {r['total_ms']:.0f}ms (target <2000ms for 10M with polars, <3000ms with pandas)")
            if args.per_col:
                print(f"  per_col: {r['per_col']}")
                print(f"  duplicated_ms: {r['duplicated_ms']} describe_ms: {r['describe_ms']}")
        # also capture json per run
    # pandas
    r2 = bench_profile(tmp, use_polars=False, per_col=args.per_col)
    results.append(r2)
    if not args.json and not args.quiet:
        print(f"Load {tmp.name} use_polars=False: {r2['read_ms']:.0f}ms shape=({r2['rows']}, {r2['cols']})")
        print(f"Profile use_polars=False: {r2['profile_ms']:.0f}ms cols={r2['cols']}")
        print(f"Total {r2['total_ms']:.0f}ms")
        if args.per_col:
            print(f"  per_col: {r2['per_col']}")
            print(f"  duplicated_ms: {r2['duplicated_ms']} describe_ms: {r2['describe_ms']}")
    if args.json:
        out = results[0] if len(results)==1 and args.no_polars else results
        # if two results, output as dict with keys polars/pandas for easy grep
        if len(results)==2:
            payload = {"polars": results[0], "pandas": results[1], "rows": args.rows, "cols": args.cols}
        else:
            payload = results[0] if results else {}
        s = json.dumps(payload, indent=2)
        if args.out:
            Path(args.out).write_text(s)
            if not args.quiet:
                print(s)
                print(f"Wrote {args.out}")
        else:
            print(s)
