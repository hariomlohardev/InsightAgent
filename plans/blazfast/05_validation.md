# BF Validation & Benchmarks — How We Prove Blazing (not just claim it)

> **Rule:** Every level has a one-liner that prints a number; if that number doesn’t beat the gate, the level isn’t done. No “looks faster” — only `grep`able.

## 1. Harness (BF-01 creates, all levels reuse)

**New flags:**
```bash
# Already in scripts/bench_profile.py — add --json --per-col
python scripts/bench_profile.py --rows 1000000 --json --per-col > /tmp/bench.json
# Output:
# {"rows":1000000,"cols":5,"read_ms":410,"profile_ms":240,"per_col":[{"name":"Sales","null_ms":12,"nunique_ms":8}],"duplicated_ms":12,"total_ms":650}

# New helper
python scripts/bench_read.py --rows 1000000 --engine polars,parquet,pandas | tee /tmp/bench_read.json
# locust parser
python scripts/bench_locust_parse.py --csv /tmp/locust_stats.csv --p95 150 --expect-hit-rate 0.6
```

**Headers (BF-03):**
```bash
curl -i http://localhost:8000/api/datasets/<id> | grep -E "X-Cache|X-Profile-Ms|X-Read-Ms"
# X-Cache: HIT
# X-Profile-Ms: 240
# X-Read-Ms: 410
```

## 2. Per-level gates (copy-paste)

### BF-01 Measure
```bash
USE_POLARS=true python scripts/bench_profile.py --rows 1000000 --json | python -m json.tool | grep -q '"total_ms"' && echo "BF-01 JSON ok"
py-spy record -o /tmp/flame.svg -- python scripts/bench_profile.py --rows 1000000 --quiet && ls -lh /tmp/flame.svg
PYTHONPATH=backend /tmp/venv09/bin/python -m pytest backend/tests/test_performance.py -q  # still 5 passed
```

### BF-02 Hot Path
```bash
# polars 1M <400ms total (was 800ms)
USE_POLARS=true python scripts/bench_profile.py --rows 1000000 --json | python -c "import json,sys; d=json.load(sys.stdin); assert d['total_ms']<400, d"
# pandas fallback still <800ms (was 1400ms)
USE_POLARS=false python scripts/bench_profile.py --rows 1000000 --json | python -c "import json,sys; d=json.load(sys.stdin); assert d['total_ms']<800, d"
PYTHONPATH=backend /tmp/venv09/bin/python -m pytest backend/tests/test_profiling.py backend/tests/test_performance.py -q
```

### BF-03 Cache
```bash
# HIT <10ms
PYTHONPATH=backend /tmp/venv09/bin/python -m pytest backend/tests/test_performance.py::test_cache_hit_lt_10ms -q
# Manual
curl -i http://localhost:8000/api/datasets/<id> | grep -q "X-Cache: MISS" && curl -i http://localhost:8000/api/datasets/<id> | grep -q "X-Cache: HIT"
# Chat cache
curl -s -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"dataset_id":"<id>","query":"sum Sales"}' | grep -q "X-Cache"
```

### BF-04 Storage
```bash
# 100MB upload <2s, no OOM
time curl -F file=@/tmp/100MB.csv http://localhost:8000/api/datasets/upload | grep '"rows"'
docker stats --no-stream --format "{{.MemUsage}}" | grep backend
python scripts/bench_read.py --rows 1000000 | grep parquet  # 40ms vs 120ms
```

### BF-05 Frontend
```bash
curl -s http://localhost:8000/api/datasets/<id> | python -c "import json,sys; d=json.load(sys.stdin); assert len(json.dumps(d['profile']['describe'])) < 10000, 'describe not trimmed'"
# AppTest (headless)
PYTHONPATH=backend /tmp/venv09/bin/python -m pytest frontend/tests -q  # or AppTest
```

### BF-06 Scale
```bash
locust --headless -u 50 -r 10 --run-time 30s -H http://localhost:8000 --csv /tmp/locust && cat /tmp/locust_stats.csv | python scripts/bench_locust_parse.py --p95 150
locust --headless -u 100 -r 20 --run-time 30s -H http://localhost:8000 --csv /tmp/locust100 && cat /tmp/locust100_stats.csv | python scripts/bench_locust_parse.py --p95 150
```

**Final gate (all must print PASS):**
```bash
USE_POLARS=true python scripts/bench_profile.py --rows 10000000 --json | python -c "import json,sys; d=json.load(sys.stdin); assert d['total_ms']<900, d['total_ms']"
locust --headless -u 50 -r 10 --run-time 30s -H http://localhost:8000 --csv /tmp/final && python scripts/bench_locust_parse.py --csv /tmp/final_stats.csv --p95 150
PYTHONPATH=backend /tmp/venv09/bin/python -m pytest backend/tests -q  # full 150+ (ignore test_performance if 10M)
```

## 3. CI integration

- `pytest -m "not slow"` runs 1M bench (not 10M) on every PR; `10M` is `pytest.mark.slow` manual nightly.
- `.github/workflows/ci.yml` add job `bench` that runs `bench_profile --rows 1000000 --json` and fails if `total_ms > 400` (polars) or `>800` (pandas).
- `BENCHMARKS.json` committed with commit hash, `BENCHMARKS.md` human table updated per level (bot can do).

## 4. What “verified blazing” looks like in PR

PR description must paste:

```
Bench 1M polars: 380ms -> 240ms (-37%) [link to BENCHMARKS.json]
Cache HIT: 6ms -> 4ms
Locust 50u p95: 85ms -> 55ms
Payload: 120KB -> 32KB
pytest: 151 passed
```

If any row missing, reviewer requests changes.

## 5. Manual checks that cannot be automated (do them once per release)

- Upload real 200MB 10M CSV via UI (drag-drop) → no spinner >2s, preview shows 10 rows, `st.json` not hanging.
- Chat 5 queries in a row on same dataset → second same query returns in <5ms (observe `X-Cache: HIT` in browser Network tab).
- `docker compose up` without `REDIS_URL` still HIT <10ms (FS fallback).
- `USE_POLARS=false docker compose up` still profiles 1M in <800ms.

## 6. Failure modes & what to do

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `total_ms` not <400 after BF-02 | `nunique` still per-col | Check `--per-col` log, ensure vectorized |
| HIT 30ms not 6ms | Redis not used but LRU evicted (1000 cap) | Increase LRU 1000→5000 or reduce `CACHE_TTL` churn |
| Upload OOM | Double read still happening | Check `datasets.py` single-pass flag `DEBUG_READ=1` |
| Frontend 120KB still | `describe` not trimmed | `curl | wc -c` vs `grep describe` |
| Locust p95 180ms | `Semaphore(20)` too tight | Raise to 40, check `X-Concurrency` |
