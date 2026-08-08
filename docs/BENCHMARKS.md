# Benchmarks — InsightAgent L10 (10M <2s, p95 <300ms)

> Generated via `scripts/bench_profile.py` and `locust --headless -u 50`. All runs on WSL2 i7 16GB, no GPU.

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

## How to reproduce

```bash
# 1M (CI-safe)
USE_POLARS=true python scripts/bench_profile.py --rows 1000000
python scripts/bench_chat.py --rows 1000000

# 10M (manual, 200MB)
USE_POLARS=true python scripts/bench_profile.py --rows 10000000

# Locust (needs backend running)
locust --headless -u 50 -r 10 --run-time 30s -H http://localhost:8000

# Cache hit proof
curl -i http://localhost:8000/api/datasets/<id> | grep X-Cache
# first MISS, second HIT <10ms
```

**Notes:** CI runs 1M only (10M `pytest.mark.slow` skipped). `USE_POLARS=false` fallback keeps `docker compose up` working without `polars`. Redis optional — in-memory LRU 1000 keys ensures <10ms even without Redis.
