"""Bench profile — 1M/10M CSV <2s via polars scan_csv."""
import time
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

def gen_csv(path: Path, rows: int, cols: int = 5):
    # Generate random CSV with 5 cols: id, value, category, date, flag
    print(f"Generating {rows} rows x {cols} cols -> {path} ...")
    # Use chunks to avoid OOM for 10M
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
        # trim to cols if needed
        if cols < 5:
            df = df.iloc[:, :cols]
        df.to_csv(path, mode="w" if not header_written else "a", header=not header_written, index=False)
        header_written = True
        print(f"  {end}/{rows}")

def bench_profile(csv_path: Path, use_polars: bool):
    from app.core.storage import load_dataset_df
    from app.core.profiling import profile_dataframe
    import tempfile, shutil
    from pathlib import Path as P
    # Simulate upload via storage
    from app.core.storage import _datasets_dir
    # Use load directly
    start = time.time()
    # Load via polars or pandas path
    # Monkey set env for this bench
    import os
    orig = os.getenv("USE_POLARS")
    os.environ["USE_POLARS"] = "true" if use_polars else "false"
    try:
        df = load_dataset_df_csv(csv_path, use_polars=use_polars)
        load_ms = (time.time() - start) * 1000
        print(f"Load {csv_path.name} use_polars={use_polars}: {load_ms:.0f}ms shape={df.shape}")
        start2 = time.time()
        prof = profile_dataframe(df, dataset_id="bench", version=0)
        prof_ms = (time.time() - start2) * 1000
        print(f"Profile use_polars={use_polars}: {prof_ms:.0f}ms cols={len(prof['column_names'])}")
        total = load_ms + prof_ms
        print(f"Total {total:.0f}ms (target <2000ms for 10M with polars, <3000ms with pandas)")
        return total
    finally:
        if orig is None:
            os.environ.pop("USE_POLARS", None)
        else:
            os.environ["USE_POLARS"] = orig

def load_dataset_df_csv(csv_path: Path, use_polars: bool = False):
    # Direct load without storage wrapper, for bench
    import pandas as pd
    if use_polars:
        try:
            import polars as pl
            try:
                return pl.scan_csv(str(csv_path), infer_schema_length=1000).collect().to_pandas()
            except:
                return pl.read_csv(str(csv_path)).to_pandas()
        except ImportError:
            pass
    # pandas chunked fallback for huge
    fsize = csv_path.stat().st_size
    if fsize > 50*1024*1024:
        chunks = []
        for chunk in pd.read_csv(csv_path, chunksize=100000):
            chunks.append(chunk)
            if sum(len(c) for c in chunks) > 10_000_000:
                break
        return pd.concat(chunks, ignore_index=True)
    return pd.read_csv(csv_path)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1_000_000, help="1M or 10M")
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--no-polars", action="store_true")
    args = ap.parse_args()
    tmp = Path(f"/tmp/bench_{args.rows}.csv")
    if not tmp.exists() or tmp.stat().st_size < 1000:
        gen_csv(tmp, args.rows, args.cols)
    bench_profile(tmp, use_polars=not args.no_polars)
    # Also bench pandas fallback
    if not args.no_polars:
        bench_profile(tmp, use_polars=False)
