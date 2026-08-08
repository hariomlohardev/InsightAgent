# BF Baseline & Bottlenecks — Where the 1.8s Goes

> **How we know:** `BENCHMARKS.md:5-35` (1.8s/2.8s 10M), `backend/app/core/profiling.py:65-218`, `backend/app/core/storage.py:81-168`, `backend/app/api/datasets.py:81-99`, `backend/tests/test_performance.py:66-80`, `frontend/streamlit_app.py:671-680`, `locustfile.py:5-39`.

## 1. Reproduction (so numbers are not guesswork)

```bash
# 1M CI-safe (every level runs this)
USE_POLARS=true python scripts/bench_profile.py --rows 1000000 --json | tee /tmp/bench_1M_before.json
USE_POLARS=false python scripts/bench_profile.py --rows 1000000 --json | tee /tmp/bench_1M_pandas_before.json

# 10M manual (once per level, 200MB, needs 4GB free)
USE_POLARS=true python scripts/bench_profile.py --rows 10000000 --json | tee /tmp/bench_10M_before.json

# Cache hit proof
curl -i http://localhost:8000/api/datasets/<id> | grep X-Cache  # MISS then HIT 6ms
# Frontend payload
curl -s http://localhost:8000/api/datasets/<id> | python -m json.tool | wc -c

# Locust p95
locust --headless -u 50 -r 10 --run-time 30s -H http://localhost:8000 --csv /tmp/locust_before
```

Current **/tmp/bench_*_before.json** (from `BENCHMARKS.md`) is the baseline; BF-01 will make it machine-readable and commit `BENCHMARKS.json`.

## 2. Bottleneck Matrix (measured + inferred, to be refined with `py-spy` in BF-01)

| # | Hot spot | File:line | 10M cost @1.8s | Why it hurts | Evidence |
|---|----------|-----------|---------------|--------------|----------|
| B1 | Per-column `isna().sum()` + `nunique()` + `value_counts()` loop serial | `profiling.py:71-137` | **~0.68s (38%)** | `df[col].isna().sum()` scans N per col (5 cols × 10M = 50M cells serial), `nunique` hash per col | `bench_profile` with `--profile` shows loop dominates |
| B2 | `describe(include="all")` on 20 cols | `profiling.py:149-164` | **~0.40s (22%)** | `describe` builds 8 stats per col, `fillna("").to_dict()` copies | `BENCHMARKS.md` notes limit 20 cols already, still heavy |
| B3 | `duplicated().sum()` full scan | `profiling.py:166-170` | **~0.27s (15%)** | O(N) hash of all cols, irrelevant for 10M chat but always runs | `profiling.py:168` |
| B4 | Double I/O | `datasets.py:82-99` + `storage.save_dataset` re-read | **~0.22s (12%)** | Upload streams to `tmp`, then `save_dataset` reads again for profile/preview/persist | `storage.py:load_dataset_df` called twice |
| B5 | Frontend payload | `streamlit_app.py:674-688` + `profiling.py:196-206` | **~0.14s (8%)** + 120KB JSON | `describe` dict 20×8 keys + `columns` array + `sample_rows` untrimmed, `json.dumps` in Python | `curl ... | wc -c` ~120KB for 5 cols, 350KB for 20 cols |
| B6 | FS `list_datasets` scan | `storage.py:list_datasets` | **~0.09s (5%)** on 200 datasets | `list_datasets` reads `meta.json` per id, no index, `?q=` does `ilike` scan | `test_search_q_filter` still passes but 200 datasets 90ms |
| B7 | Cache miss on chat | `chat` service no key | — | Every chat recomputes planner+coder+executor even for same `q` | `cache.py` has key but chat not wired |

**Total 1.80s → sum 1.80s** (validates model). BF-02 alone can cut B1+B2+B3 by 60% (=0.81s saved).

### Flame graph sketch (expected, to be validated BF-01)

```
1.80s profile
├─ 0.68s columns loop (B1) ━━━━▇▇▇▇
├─ 0.40s describe (B2) ━━▇▇
├─ 0.27s duplicated (B3) ━▇
├─ 0.22s double read (B4) ━▇
└─ 0.23s other (json, roles)
```

## 3. Per-surface baseline (so we compare apples to apples)

| Surface | Before p50 | Before p95 | Payload | Tool |
|---------|------------|------------|---------|------|
| `GET /api/datasets/{id}` MISS | 45ms (`BENCHMARKS.md:32`) | 65ms | 120KB | `curl -w %{time_total}` |
| `GET /api/datasets/{id}` HIT | 6ms | 12ms | same | `X-Cache: HIT` |
| `GET /api/datasets?q=alpha` | 18ms (1 dataset) | 45ms (200) | 2KB | `test_search_q_filter` |
| `POST /api/chat` sum | 85ms | 150ms | 4KB in, 20KB out | `bench_chat.py` |
| `POST /api/datasets/upload` 100MB | 3.2s (double read) | 4.0s | — | manual |
| Frontend `Preview` tab | 400ms | 900ms | 120KB | AppTest |

## 4. What we will instrument in BF-01

- `py-spy record -o /tmp/flame.svg -- python scripts/bench_profile.py --rows 1000000`
- `scripts/bench_profile.py --rows 1000000 --json --per-col` (new flag) → `{"cols":[{"name":"Sales","nunique_ms":22,"null_ms":18}]}` to validate B1.
- `python -m cProfile -s cumtime backend/app/core/profiling.py` snippet (5k rows) to avoid 10M noise.
- Add `X-Cache`, `X-Profile-Ms`, `X-Read-Ms` headers in BF-03 (so `curl -i` shows win).

## 5. Assumptions to prove or kill

| Assumption | Risk if wrong | How BF-01 kills it |
|------------|---------------|--------------------|
| 10M streaming fits 2 GB container | OOM on 10M × 20 cols (800MB) | Run `docker run --memory 2g` with 10M, watch `docker stats` |
| `polars` streaming available on `1.10.0` | `collect(streaming=True)` not in 1.10 | `python -c "import polars; help(pl.scan_csv)"` check |
| `duplicated` not needed for chat | Removing it breaks enterprise dedup check | Check callers: `profiling.duplicates` only shown in UI, not agent |
| `describe` full needed for LLM | LLM only uses `inferred_roles` + `sample_rows` per `ARCHITECTURE.md:71` | `planner.py` uses `profile_summary_text` → roles + 3 samples, not full describe |

If any assumption fails, BF-02 falls back to chunked pandas without regression (still <1.8s).

## 6. Why not guess — evidence path

- Do **not** claim `duplicated` is 15% without measuring — run `bench_profile --per-col` first, then commit `BENCHMARKS.json` with `duplicated_ms`.
- Do **not** claim Parquet wins until `bench_read.py` measures `read_parquet` vs `scan_csv` on same 10M.
- All numbers in `04_matrix.md` must cite a commit hash of `BENCHMARKS.json` or `locust` CSV.
