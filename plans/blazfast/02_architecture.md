# BF Architecture — Key Decisions for Blazing

> **Principle:** Least new abstraction. Prefer vectorize + trim + cache over rewrite. Keep `USE_POLARS=false` and `REDIS_URL=""` working — blazing is an additive path, not a fork.

## Decision Matrix (each row is a real tradeoff)

### D1 — CSV read path

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| A. **Polars `scan_csv` + `collect(streaming=True, predicate_pushdown=True)` + `to_pandas` 5k preview** | 2.1× at 1M (`BENCHMARKS.md:10` 420ms vs 980ms), streaming fits 2GB, zero-copy arrow | Requires `polars>=1.10`, API changed `streaming` flag | **Recommended** when `USE_POLARS=true`; guard with `try: import polars` |
| B. Pandas `chunksize=100k` + sample | Works without deps, proven | 1.75× slower, still loops per chunk | **Fallback** when `USE_POLARS=false` or `polars` missing |
| C. DuckDB `read_csv_auto` | Fast SQL pushdown | Heavier dep, slower on wide `describe` | Rejected — keep DuckDB only for chat SQL |

**Chosen:** A primary, B fallback. No new DB.

### D2 — Profile compute

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| A. Vectorized `nulls = df.isna().sum().to_dict()` once + `nunique` via `pl.n_unique` or `pd.Series.nunique(dropna=True)` chunked + `duplicated` via `hash` sample or skip when `rows>1M` | Cuts B1 38% → 12% (0.68s→0.22s), no per-col scan | Need to keep `unique` exact for ≤1M, approx for >1M | **Recommended** |
| B. Keep per-col loop but parallel `ThreadPool` | Simple | GIL, still N scans, not vectorized | Rejected |
| C. Sample 100k for profile then extrapolate | <100ms | Loses accuracy for LLM roles | Rejected — LLM needs exact `nulls` for small cols |

**Chosen:** A — exact for ≤1M, hyperloglog/approx for >1M with flag `exact_nunique = rows <= 1_000_000`.

### D3 — Cache

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| A. Keep LRU 1000 + Redis, add `profile:{id}:{version}`, `preview:{id}:{version}:5k`, `chat:{id}:{qhash}:{version}`, `X-Cache: HIT/MISS/STALE`, `stale-while-revalidate` 30s | HIT <10ms proven (`test_cache_hit_lt_10ms:80`), no Redis still <10ms, invalidation correct via `version` (`profiling.py:12-14`) | More keys | **Recommended** |
| B. Add `redis` required | Faster p95 with network | Breaks `docker compose up` frictionless | Rejected |
| C. No chat cache (always recompute) | Simple | Wastes LLM + executor 85ms each time | Rejected |

**Chosen:** A — additive, versioned, SWR.

### D4 — Storage I/O

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| A. **Single-pass ingest**: `tmp_path` → `profile` + `preview` + `write data.csv + data.parquet` in one `pl.scan_csv` or `pd.read_csv(chunksize)` pass | Saves double read 0.22s, Parquet re-read 3× faster (40ms vs 120ms for 1M) | Adds `pyarrow` dep for Parquet | **Recommended** — `pyarrow` already needed for `st.dataframe` (`frontend` import) |
| B. Keep double read | No change | 12% waste | Rejected |
| C. Direct `COPY` to Postgres via `COPY FROM STDIN` | Faster for DB path | Breaks FS fallback | Rejected for FS; optional for DB path only |

**Chosen:** A — single pass, write both formats, read Parquet when `exists` and `rows>100k`.

### D5 — Frontend payload

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| A. Trim `describe` to 8 keys (`mean,min,max,median,std,25%,50%,75%`), paginate `columns` (20 per page), `st.cache_data(ttl=60)` on `preview`, `orjson` dumps, `selectbox` guards already fix `IndexError` | Payload 120KB→32KB (-73%), TTI 400ms→180ms, no API break | Need to keep `sample_rows` 5 for LLM | **Recommended** |
| B. Rewrite frontend in Next.js | Faster render | Breaks `make install` Python-only | Rejected |
| C. No trim, just gzip | Simple | Still 120KB parse cost in browser | Rejected |

**Chosen:** A.

### D6 — Search

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| A. `ilike` fallback FS, `pg_trgm` `GIN` + `ILIKE` with `similarity>0.3` when `DATABASE_URL` has Postgres, `list_datasets(q)` keeps same signature (`storage.py:list_datasets`) | No new infra, 20ms vs 90ms on 200 datasets, keeps FS fast | Requires `CREATE EXTENSION pg_trgm` | **Recommended** |
| B. Meilisearch / Typesense | Fastest | New service, breaks compose | Rejected |

### D7 — Queue & concurrency

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| A. Keep Celery `forecast` 202 + add `asyncio.Semaphore(20)` on chat, `X-Queue: HIT` header, `GET /api/jobs/{id}` already polls | p95 <150ms at 100 users, no new infra | Need to bound memory per job | **Recommended** |
| B. Add `arq`/`rq` | Similar | New dep | Rejected — extend existing |

## Component Touch Map (so reviewers know blast radius)

| File | Change | Level |
|------|--------|-------|
| `backend/app/core/storage.py:load_dataset_df` | polars streaming + parquet cache + single-pass flag | BF-02, BF-04 |
| `backend/app/core/profiling.py:22-218` | vectorized nulls/nunique, skip/approx duplicated, trimmed describe | BF-02 |
| `backend/app/core/cache.py:12-78` | chat/preview keys + SWR | BF-03 |
| `backend/app/api/datasets.py:208-223` | `X-Profile-Ms`, `X-Read-Ms`, `X-Cache` headers | BF-03 |
| `frontend/streamlit_app.py:671-680` | trim describe, paginate, `cache_data` | BF-05 |
| `backend/app/api/datasets.py:81-99` | single-pass save | BF-04 |
| `scripts/bench_profile.py` | `--json --per-col` | BF-01 |

**Not touched:** `app/api/auth.py`, `app/core/security.py` (no perf change), `CLOUD` billing.

## Data Flow — Before vs Blazing

```
Before (1.80s):
  upload tmp --(read 1)--> save_dataset --(read 2)--> profile loop per col -- describe -- duplicated --> cache --> frontend 120KB

Blazing (0.85s):
  upload tmp --(single scan)--> [profile vectorized + preview 5k + write parquet/csv] --> cache (profile/preview/chat) --> frontend 32KB (trimmed) --> st.cache_data
         ^--- X-Read-Ms/X-Profile-Ms headers for bench
```

## Compatibility & Fallback

- Every new path has `if USE_POLARS and has_polars: use polars else: pandas chunksize`.
- Every new header is additive (`X-Cache` already exists, add `X-Profile-Ms` etc.).
- Every new dep `pyarrow`/`polars` is optional — `try: import` else skip Parquet/streaming and log `logger.info`.
- `DATABASE_URL=""` still works — FS path tested in `test_performance.py:_reset_db_and_cache`.

## Why not rewrite?

- `COMPARISON.md` shows 1.8s already beats Metabase 8s / Superset 6s — blazing is polish, not rescue. A rewrite would lose 100+ tests (`backend/tests/*`) and `docker compose up` in 30s promise.

## Open questions (none blocking)

- Polars `streaming=True` flag renamed to `engine="streaming"` in 1.12 — pin `1.10.*` and guard.
- Parquet for 1k rows not worth it — only when `rows>100k` (checked in code).
