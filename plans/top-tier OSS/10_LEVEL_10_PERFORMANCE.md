# Level 10 — Performance & Scale: 10M in <2s, p95 <300ms (8.0 → 8.5)

> **From “works for 1k rows” to “works for 10M rows and 100 users”.**

## Goal

Prove speed, not claim it. Make `profile`, `chat` (groupby), `dashboard refresh` meet L7’s <3s/<2s/<1s at 10M, and `GET /api/datasets` p95 <300ms at 50 concurrent users.

## Success Criteria

- [ ] `profile` 10M-row CSV (generated 200MB) <2s via `pl.scan_csv` when `USE_POLARS=true` else <3s via chunked `pandas`; `chat` groupby <2s; each widget refresh <1s (measured `pytest --benchmark` or `python scripts/bench_profile.py`)
- [ ] Cache hit <10ms: `GET /api/datasets/{id}` + `profile` cached in Redis `CACHE_TTL=60` with `cache_key(profile:dataset:version)`; hit metric logged
- [ ] Upload 100MB streaming (no OOM): `UploadFile` chunked 8KB → `tempfile` + `async` `save_dataset` with progress
- [ ] Search: `pg_trgm` or `pgvector` for dataset name search `?q=` (optional, fallback `LIKE`)
- [ ] `locustfile.py` 50 users (`GET /api/datasets`, `POST /api/chat` small) p95 <300ms doc’d to `BENCHMARKS.md`
- [ ] `pytest` 150+ (add 5), `BENCHMARKS.md` with numbers, `docker-compose up` still OOM-safe without Redis

## Context & Current Facts

- `profiling.py` already caches `profile` 60s but keys by `shape`, not `dataset version`; `cache.py` has Redis + in-memory LRU 1000 keys.
- `storage.py` `pd.read_csv` loads whole file; 10M (800MB with 20 cols) OOMs on 2GB container. Polars `pl.scan_csv` + `pl.read_csv batched` needed.
- No `locustfile.py`, no `BENCHMARKS.md`. `MAX_UPLOAD_MB=100` but uploads read `await file.read()` fully into memory.
- Queue already 202 for `forecast`/>1M; scale needs streaming, not just queue.

## Constraints

- Keep `USE_POLARS=false` fallback working (contributor without `polars`). Keep `REDIS_URL` optional.
- No GPU required; `ollama` still optional.

## Key Decisions

| Decision | Recommended | Why |
|----------|-------------|-----|
| CSV read | `polars==1.10.0` `pl.scan_csv` + `collect` when `USE_POLARS=true` else `pandas chunksize=100k` sample 20 cols for `describe` | 10x at >1M, fallback keeps compat |
| Upload | `shutil.copyfileobj(file.file, tmp, 8192)` streaming, not `await file.read()` | Avoid 100MB RAM spike |
| Load test | `locust==2.20` `locustfile.py` | Standard, 1 file |
| Search | `sqlalchemy` `ilike` fallback, `pg_trgm` when `DATABASE_URL` | No new DB |

## Work Plan

### 10.1 — Read Path (1d)
- `storage.load_dataset_df(dataset_id, use_polars)` → `pl.scan_csv` + `df_pl.to_pandas()` limit 5000 preview, `profile_dataframe` sample 20 cols if cols>20 (already) + `describe` chunked

### 10.2 — Upload Streaming + Cache Keys (1d)
- `datasets.py` `upload_dataset` chunked copy, `profiling.py` `cache_key(f"profile:{dataset_id}:{version}")` + `chat` `cache_key(chat:{id}:{hash(query)}:{version})` (already) but wire `version` correctly, add `X-Cache: HIT` header for bench

### 10.3 — Search + pgvector Optional (0.5d)
- `GET /api/datasets?q=` filters `original_filename ilike`, `storage.list_datasets(q)`

### 10.4 — Bench (1d)
- `scripts/bench_profile.py` generates 1M/10M CSV, times `profile_dataframe`, `scripts/bench_chat.py`, `locustfile.py`, `BENCHMARKS.md` committed with run numbers (CI can be manual)

**Total 3.5d**

## Validation Plan

| Check | Command | Expected |
|-------|---------|----------|
| Profile | `USE_POLARS=true python scripts/bench_profile.py --rows 1000000` | <3s printed |
| Cache | `pytest tests/test_cache.py -v` | hit <10ms assert |
| Upload | `MAX_UPLOAD_MB=100 pytest tests/test_upload_edge.py::test_upload_large` | streaming, not OOM |
| Locust | `locust --headless -u 50 -r 10 --run-time 30s -H http://localhost:8000` | p95 <300ms in log |
| Regression | `pytest -q` | 150+ |

## Risks

- Polars not installed → `try: import polars` falls back, test skips 10M bench with warning.
- 10M CSV generation heavy in CI → mark `pytest.mark.slow`, CI runs 1M only, 10M manual.

## Open Questions

- None. Polars version pinned, chunk fallback proven.
