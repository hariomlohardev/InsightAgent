# BLAZFAST — Overview: From Fast to Blazing Fast (1.8s → <0.9s for 10M)

> **Goal:** Make InsightAgent feel instant on 10M-row CSVs and 100 concurrent users without losing MIT, `docker compose up`, or `USE_POLARS=false` frictionlessness. No GPU required. No rewrite — harden hot paths already proven in L10.

**Where this lives:** `plan/blazfast/` (mirrored to `plans/blazfast/` for compatibility). Code stays in `backend/app/core/*`, `frontend/streamlit_app.py`, `scripts/bench_*`, `BENCHMARKS.md`. This is plan-only — no code in this phase.

## Goal

- **User story:** A hacker drops a 200 MB CSV (10M × 5) or connects Postgres, asks `sum Sales by Region`, and sees table+chart in <0.9s p50 / <1.5s p95 on a 2 vCPU / 4 GB laptop; 50 users chatting still p95 <150ms; upload 100 MB never OOMs; Streamlit preview renders in <500 ms.
- **Scope:** Backend read/profile/chat, cache, storage I/O, frontend payload & render, queue/concurrency, observability. Out of scope: new LLM providers, new connectors, UI redesign.

## Success Criteria (must be true to call it "blazing")

| Outcome | Before (L10, `BENCHMARKS.md:5-35`) | Blazing target | How we prove |
|---------|-----------------------------------|----------------|--------------|
| Profile 10M 5 cols | 1.8s `USE_POLARS=true` (polars scan), 2.8s pandas | **<0.9s** polars, **<1.8s** pandas | `USE_POLARS=true python scripts/bench_profile.py --rows 10000000` |
| Profile 1M 5 cols | 0.80s polars / 1.40s pandas | **<0.40s** / **<0.80s** | same, 1M CI |
| Chat groupby 1M | 45ms pandas, 32ms DuckDB | **<25ms** DuckDB path, cache hit <5ms | `python scripts/bench_chat.py` |
| Dashboard widget 100k | 8ms | **<5ms** | same |
| Cache HIT | 6ms (target <10ms) | **<6ms** p50, **<10ms** p95 | `pytest backend/tests/test_performance.py::test_cache_hit_lt_10ms` + `curl -i /api/datasets/{id}` |
| Locust 50 users p95 | 85ms (Redis) / 120ms (FS) | **<60ms** Redis, **<100ms** FS, **p95 <150ms** overall | `locust --headless -u 50 -r 10 --run-time 30s` |
| Upload 100 MB | streaming 8KB works, but no progress | **<2s** ingest + no RAM spike >200 MB | `test_upload_streaming_large` + `docker stats` |
| Frontend preview | `st.dataframe` full 10 rows + `st.json` | **<500ms** TTI via trimmed payload + `st.cache_data` | AppTest timing + manual stopwatch |
| Storage list `?q=` | `ilike` scan | **<20ms** with trigram/FTS when DB, still <100ms FS | `pytest` + `EXPLAIN ANALYZE` |

If any row regresses >10% vs L10, blazing is not done.

## Context And Current Facts (grounded)

**L10 already ships (evidence):**

- `backend/app/core/profiling.py:6-35` caches `profile:{dataset_id}:{version}` 60s, handles empty/wide (>20 cols) via `describe` limit, but `df.duplicated().sum()` and `value_counts()` still scan full 10M.
- `backend/app/core/cache.py:12-78` Redis optional + in-memory LRU 1000 keys, `cache_key()` hashed >120 chars, `CACHE_TTL=60`.
- `backend/app/core/storage.py:81-168` `load_dataset_df()` supports `use_polars` → `pl.scan_csv` + `collect`, but `profile_dataframe` still builds `columns` loop per column with `isna().sum()` + `nunique()` serially.
- `backend/app/api/datasets.py:81-99` upload streams 8KB chunks to `NamedTemporaryFile`, checks 100 MB, but `storage.save_dataset` re-reads whole file for preview/profile (double I/O).
- `frontend/streamlit_app.py:674-675` `st.dataframe(df_prev)` + `st.json(profile.get("null_summary",{}))` renders full `describe` dict (can be 20×8 keys) untrimmed.
- `BENCHMARKS.md:5-48` 1M 0.8s/1.4s, 10M 1.8s/2.8s, locust p95 85ms, HIT 6ms — on WSL2 i7 16GB, no GPU.
- `backend/tests/test_performance.py:66-80` asserts HIT <50ms (allows CI slack), version invalidation works.
- `plans/top-tier OSS/10_LEVEL_10_PERFORMANCE.md:18-38` keeps `USE_POLARS=false` fallback and `REDIS_URL` optional — blazing must keep both.

**Bottlenecks found (see `01_baseline.md`):** profile loop 38% of 1.8s, `describe` 22%, `nunique` 15%, double read 12%, Streamlit JSON serialize 8%, FS `list_datasets` scan 5%.

## Constraints And Non-goals

**Hard constraints (from `CONTRIBUTING.md`, `ARCHITECTURE.md`, `.env.example`):**
- Keep `AUTH_REQUIRED=false`, `CLOUD=false` defaults; `docker compose up` works without `DATABASE_URL` / `REDIS_URL` / `polars`.
- MIT, Python-buildable, no `npm` rebuild, no GPU.
- Keep `USE_POLARS=false` fallback — polars is optional, not required.
- Keep API shape: `GET /api/datasets`, `GET /api/datasets/{id}` with `X-Cache`, `POST /api/chat`, etc. No breaking SDK.
- 8px/12px radii, one accent hsl(160) — no perf trade that breaks tokens.

**Non-goals:**
- New connectors, new LLM providers, UI token redesign, vector DB, GPU kernels, rewriting Streamlit in Next.js.

## Key Decisions (summary — details in `02_architecture.md`)

| Decision | Recommended | Rejected & why |
|----------|-------------|----------------|
| 1. Read path | Polars `scan_csv` + `collect(streaming=True)` + `predicate_pushdown` + zero-copy arrow → pandas preview 5k, plus pandas `chunksize=100k` fallback | Arrow-only DB would break `USE_POLARS=false`; DuckDB `read_csv` alone slower on wide cols |
| 2. Profile | Vectorized `nulls = df.isna().sum()` once, `nunique` via `pl.n_unique` or `pd` `hash` chunked, `describe` only on numeric sample 20 cols, `duplicated` via hash not full scan for >1M | Per-column loop is 38% of time; full `duplicated` O(N) too heavy |
| 3. Cache | Keep LRU + Redis, add `chat:{id}:{qhash}:{version}` + `profile` + `preview` keys, add `stale-while-revalidate` + `X-Cache: STALE` | Removing LRU would regress without Redis (FS p95 120ms) |
| 4. Storage | Single read: `tmp_path` → `profile` + `preview` + `persist` in one pass, Parquet cache `data.parquet` for re-read 3× faster | Double read now costs 12%; Parquet not required for 1k rows but wins at 10M |
| 5. Frontend | Trim `describe` to 8 keys, paginate `columns` expander, `st.cache_data(ttl=60)` for preview, `orjson` serialization | Sending full describe 20×8 keys bloats payload 4× |
| 6. Validation | `scripts/bench_profile.py --rows 10000000 --json` machine-readable + CI gate `pytest -m "not slow"` | Manual only would not catch regression |

## Recommended Approach (phased, no rewrite)

Run **6 levels BF-01…BF-06** in order (see `03_levels.md`). Each level is shippable, measured, and rollback-safe. Levels 01–02 give 40% win alone; 03–04 give next 30%; 05–06 polish to p95.

## Work Plan (high-level)

1. **BF-01 Measure** — harness + flame graph + `BENCHMARKS.md` machine-readable (1d)
2. **BF-02 Hot Path** — profile vectorize + arrow read (2d)
3. **BF-03 Cache** — versioned chat/profile/preview + SWR + headers (1d)
4. **BF-04 Storage I/O** — single-pass ingest + Parquet + DB index (1.5d)
5. **BF-05 Frontend** — payload trim + cache_data + pagination (1d)
6. **BF-06 Scale** — queue, concurrency, locust p95, OTEL pprof (1.5d)

Total **8d** engineering + 1d docs. Each level has its own validation gate.

## Validation Plan (evidence)

- Every level: `PYTHONPATH=backend /tmp/venv09/bin/python -m pytest backend/tests -q` (subset) + `USE_POLARS=true python scripts/bench_profile.py --rows 1000000 --json` before/after.
- Final: 10M run, locust 50/100 users, cache header drill, `docker stats` memory, AppTest `st.json` payload size.
- Manual: upload 100 MB CSV, chat 5 queries, dashboard 3 widgets, check `GET /health` `db.latency_ms`.

## Risks / Rollback

- Polars `streaming` flag changes per version → pin `polars==1.10.*`, fallback to `collect()` if `streaming` unsupported, test `USE_POLARS=false` still <1.8s.
- Parquet adds dep `pyarrow` — already required for `st.dataframe`; if missing, skip cache and log.
- Redis unavailable → LRU still <10ms HIT, but p95 degrades 60→100ms — documented, not failure.

## Open Questions

- None blocking — all facts local. One assumption: 10M run on 4 GB runner still fits with streaming (validated 200 MB CSV fits 2 GB container per L10). Mark as assumption to verify in BF-01.
