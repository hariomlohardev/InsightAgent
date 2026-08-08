# BF Risks, Rollback & Non-goals

## Risks (likelihood × impact, with mitigation)

| # | Risk | L × I | Mitigation | Rollback |
|---|------|-------|------------|----------|
| R1 | Polars `streaming` flag renamed/broken in 1.10→1.12 | M×H | Pin `polars==1.10.*` in `backend/requirements.txt`, guard `try: collect(streaming=True) except TypeError: collect()` | Revert to `pd.read_csv(chunksize)` — still <1.8s, gate BF-02 `USE_POLARS=false` ensures no regression |
| R2 | Parquet adds `pyarrow` heavy dep, breaks `docker compose` on ARM | L×M | `pyarrow` already needed for `st.dataframe`; guard `try: import pyarrow` else skip parquet with `logger.info("parquet skip")` | Delete `data.parquet` logic, keep `data.csv` only |
| R3 | Vectorized `nunique` approx for >1M loses accuracy for LLM | L×M | `exact = rows<=1_000_000` (most user files <1M); for >1M show `unique_approx` in UI, keep `nulls` exact | Revert to exact `nunique` per col but keep vectorized `isna` |
| R4 | Cache SWR serves stale profile after `apply_clean` version bump | M×H | `profile:{id}:{version}` key already versioned (`profiling.py:12-14`), `create_version` increments `current_version`, `clear_prefix(profile:{id})` on write | Remove SWR, keep 60s TTL only |
| R5 | DB `pg_trgm` `CREATE EXTENSION` needs superuser, fails on managed DB | M×M | `try: create extension` else fall back to `ilike` scan (FS path), log `pg_trgm not available` | No migration, keep `ilike` |
| R6 | Frontend trim hides `describe` keys that enterprise audit expects | L×M | Keep full `describe` in `GET /api/datasets/{id}` raw, trim only `preview` + Streamlit `st.json` display; API shape unchanged | Revert `streamlit_app.py` trim, keep backend full |
| R7 | Locust 100u p95 breaches 150ms on 2GB runner (CI flaky) | M×M | Run locust on 4GB runner manual, CI gate is 50u <150ms; 100u is nightly not PR gate | Raise gate to 200ms for CI, keep 150ms for release |
| R8 | `duplicated().sum()` skip breaks dedup audit for >1M | L×L | `duplicates` only shown in UI (`profiling.py:166`), not used by agent; show `duplicates_approx` or `">1M skipped"` | Restore full `duplicated` behind `if rows<500k` |

## Rollback Plan (per level, 5 min)

1. **BF-01:** `git revert <bf01-commit>` — only scripts, no runtime impact.
2. **BF-02:** `git revert` + set `USE_POLARS=false` in `.env` → back to 1.40s pandas (still L10 1.8s budget). No DB change.
3. **BF-03:** `CACHE_TTL=60` + remove `chat` key logic → HIT still 6ms (profile), chat recomputes 85ms (acceptable). Clear Redis `redis-cli FLUSHDB` or LRU `clear_prefix("chat")`.
4. **BF-04:** Delete `data.parquet` files, revert `datasets.py` single-pass → double read 3.2s again but no OOM. No migration revert needed.
5. **BF-05:** Revert `streamlit_app.py` trim → payload 120KB again, still functional.
6. **BF-06:** Remove `Semaphore(20)` → p95 85ms→120ms, still <150ms gate.

**Emergency full rollback:** `git revert HEAD~6..HEAD` → back to L10 1.80s tag `v1.0-blazfast-base`. Keep `BENCHMARKS.json` history for bisect.

## Non-goals (so scope doesn’t creep)

- No new LLM providers, no new connectors (`postgres/mysql/bigquery` stay), no vector DB, no GPU.
- No rewrite of Streamlit to Next.js — Python `make install` must stay.
- No breaking `GET /api/datasets` shape — additive headers only.
- No `REDIS_URL` required — FS fallback stays <10ms HIT.
- No `USE_POLARS` required — `false` still <1.8s.
- No UI token change — 8px/12px, hsl(160) stay.

## Compatibility Impact

| Surface | Change | Breaking? | Migration |
|---------|--------|-----------|-----------|
| `GET /api/datasets/{id}` | Adds `X-Profile-Ms`, `X-Read-Ms`, trims `describe` in Streamlit but not API | No — additive headers, API still full `describe` | None |
| `storage.load_dataset_df` | Adds `use_parquet` param, default `true` when `rows>100k` | No — callers without param get old CSV path | None |
| `cache` | New keys `chat:*`, `preview:*` | No | `FLUSHDB` optional |
| DB | Optional `GIN` index, `pg_trgm` | No — `try` + fallback | `alembic upgrade` creates index `CONCURRENTLY` if `DATABASE_URL` postgres |

## Monitoring (so we know blazing didn’t regress in prod)

- `GET /health` already has `db.latency_ms` — add `profile_p50_ms`, `cache_hit_rate` via OTEL span `profile_ms` (BF-06).
- `Sentry` transaction `profile` with `tags: {rows, cols, engine: "polars|pandas"}`.
- `BENCHMARKS.json` committed per level, `BENCHMARKS.md` human table, `locust --csv` artifact in CI.

## Open Questions (all answered, left for audit)

- None blocking. One assumption to verify in BF-01: 10M × 20 cols (800MB) fits 2GB with streaming — will test `docker run --memory 2g` 10M and watch `docker stats`. If not, cap `cols>20` already trims `describe`, and spill to disk via `pl.scan_csv` streaming.

## Approval Ask

This plan is **decision-complete** — reviewers can critique tradeoffs without Inventing scope. Next step is **Approve / Request changes / Cancel** before any code (per plan skill).
