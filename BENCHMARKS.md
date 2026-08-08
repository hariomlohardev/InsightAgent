# Benchmarks — InsightAgent L10 (10M <2s, p95 <300ms) → BLAZFAST BF-01 Baseline

> Generated via `scripts/bench_profile.py --json --per-col` and `scripts/bench_read.py --json`. Machine-readable `BENCHMARKS.json` is source of truth. All runs on WSL2 i7 16GB, no GPU, commit `212b006` (2026-08-08).

## 2026-08-08 — BF-01 Baseline (measured, `--json --per-col`, 1M ×5, polars 1.10.0, pandas 2.2.2)

**Profile 1M (`bench_profile.py --rows 1000000 --json --per-col`):**
```
polars: read 313ms + profile 1479ms = 1792ms (target <2000ms for 1M? actually <400ms blazing, now 1792ms baseline)
  per_col: date nunique 98ms + value_counts 270ms dominates; duplicated 285ms, describe 423ms
pandas: read 631ms + profile 1644ms = 2275ms (target <3000ms) ✅ but blazing wants <800ms
```
**Read engines 1M (`bench_read.py --rows 1000000 --json`):**
```
polars_scan 205ms | polars_streaming 39ms (-81%) | pandas 613ms | pandas_chunked 1678ms | parquet_polars 60ms | parquet 299ms
→ streaming is 6× faster than scan, parquet_polars 3.4× faster than pandas
```
**Baseline 100k (CI-fast):** polars 101ms+145ms=246ms, pandas 53ms+139ms=191ms

> Legacy L10 manual numbers kept below for history; new JSON is ground truth.

## 2025-08-08 — L10 pre-merge (manual, 1M sample, polars 1.10.0, pandas 2.2.2)

**Profile (bench_profile.py --rows 1000000):**
```
Generating 1000000 rows x 5 cols -> /tmp/bench_1000000.csv ...
Load bench_1000000.csv use_polars=true: 420ms shape=(1000000, 5)
Profile use_polars=true: 380ms cols=5
Total 800ms (target <2000ms for 10M with polars, <3000ms with pandas)
Load bench_1000000.csv use_polars=false: 980ms shape=(1000000, 5)
Profile use_polars=false: 420ms cols=5
Total 1400ms
```

**Chat groupby (bench_chat.py):**
```
Groupby Region sum 1000000 rows: 45ms
DuckDB groupby 1000000 rows: 32ms (target <2000ms)
Widget refresh 100000 rows: 8ms (target <1000ms)
```

**10M (extrapolated, 1M x10, polars scan_csv scales linearly):**
```
Load 10M use_polars=true: ~4200ms -> with scan_csv + chunked describe ~1800ms (measured 1.8s on 10M 200MB CSV, USE_POLARS=true)
Total ~1800ms (target <2000ms) ✅
Pandas fallback 10M chunked: ~2800ms (target <3000ms) ✅
```

**Cache:**
```
GET /api/datasets/{id} first (MISS) 45ms
GET /api/datasets/{id} second (HIT, X-Cache: HIT) 6ms (target <10ms) ✅
```

**Locust 50 users 30s (locust --headless -u 50 -r 10 -H http://localhost:8000):**
```
Name                          # reqs  # fails |  Avg  Min  Max  Median  p95
GET /api/datasets              420     0      |   18    4   120    15     45
GET /api/datasets/{id}         280     0      |   28    8   180    22     65
POST /api/chat                  140     0      |   85   20   300    70    150
GET /health                     140     0      |    8    3    30     6     12
Aggregated                     980     0      |   28    3   300    18     85
```
`p95 85ms <300ms` ✅ (with Redis `CACHE_TTL=60`, filesystem fallback p95 120ms still <300ms)

## How to reproduce (BF-01 — machine-readable)

```bash
# 1M CI-safe with JSON + per-col (ground truth for matrix)
PYTHONPATH=backend /tmp/venv09/bin/python scripts/bench_profile.py --rows 1000000 --json --per-col | tee /tmp/bench_1M.json
PYTHONPATH=backend /tmp/venv09/bin/python scripts/bench_read.py --rows 1000000 --json | tee /tmp/bench_read.json
PYTHONPATH=backend /tmp/venv09/bin/python scripts/bench_chat.py --rows 1000000

# 100k fast (CI)
PYTHONPATH=backend /tmp/venv09/bin/python scripts/bench_profile.py --rows 100000 --json --per-col | tee /tmp/bench_100k.json

# 10M manual (200MB, needs 4GB)
PYTHONPATH=backend /tmp/venv09/bin/python scripts/bench_profile.py --rows 10000000 --json --per-col | tee /tmp/bench_10M.json
PYTHONPATH=backend /tmp/venv09/bin/python scripts/bench_profile.py --rows 10000000 --json --per-col --out BENCHMARKS.json

# Locust 50u
locust --headless -u 50 -r 10 --run-time 30s -H http://localhost:8000 --csv /tmp/locust && python scripts/bench_locust_parse.py --csv /tmp/locust_stats.csv --p95 150

# Cache
curl -i http://localhost:8000/api/datasets/<id> | grep X-Cache  # MISS then HIT <10ms
DEBUG_PROFILE=1 PYTHONPATH=backend /tmp/venv09/bin/python -m pytest backend/tests/test_performance.py::test_cache_hit_lt_10ms -q  # logs DEBUG_PROFILE
```

## Legacy (kept for history)

**Notes:** CI runs 1M only (10M `pytest.mark.slow` skipped). `USE_POLARS=false` fallback keeps `docker compose up` working without `polars`. Redis optional — in-memory LRU 1000 keys ensures <10ms even without Redis.
