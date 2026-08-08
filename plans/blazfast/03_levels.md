# BF Levels — 6 Shippable Steps to Blazing (8d + 1d docs)

> **How to read:** Each level is a PR-sized slice, depends on previous, has its own validation gate. Do not start BF-N+1 until BF-N’s gate is green. No code in planning phase — commands are for later execution.

## Dependency Graph

```
BF-01 Measure ──▶ BF-02 Hot Path ──▶ BF-03 Cache ──▶ BF-04 Storage I/O ──▶ BF-05 Frontend ──▶ BF-06 Scale
  (1d)             (2d)               (1d)              (1.5d)                (1d)              (1.5d)
     └─────────────────────────────────────────────────────────────────────────────────────────┘
                                      1d docs & BENCHMARKS.json finalize
```

---

### BF-01 — Measure Harness (1d) — *“you can’t speed what you don’t measure”*

**Goal:** Make `BENCHMARKS.md` machine-readable and prove B1-B7 numbers.

**Work:**
- Add `scripts/bench_profile.py --json --per-col` → `/tmp/bench_1M.json` with `{"rows":1_000_000,"read_ms":420,"profile_ms":380,"per_col":[{"name":"Sales","null_ms":18,"nunique_ms":22,"value_counts_ms":15}],"duplicated_ms":270}`
- Add `scripts/bench_read.py` (read_csv vs scan_csv vs parquet on same 1M)
- Instrument `profiling.py` with optional `DEBUG_PROFILE=1` that logs `X-Profile-Ms` breakdown to stderr
- Commit `BENCHMARKS.json` (machine) + update `BENCHMARKS.md` (human) with flame graph `py-spy` output

**Files:** `scripts/bench_profile.py`, `scripts/bench_read.py`, `BENCHMARKS.json`, `BENCHMARKS.md`

**Validation gate (must pass before BF-02):**
```bash
USE_POLARS=true python scripts/bench_profile.py --rows 1000000 --json | python -m json.tool > /tmp/b1.json
cat /tmp/b1.json | grep -q "read_ms" && echo "gate BF-01 HIT"
py-spy record -o /tmp/flame.svg -- python scripts/bench_profile.py --rows 1000000 --quiet && ls /tmp/flame.svg
PYTHONPATH=backend /tmp/venv09/bin/python -m pytest backend/tests/test_performance.py -q
```

---

### BF-02 — Hot Path: Profile Vectorize + Arrow Read (2d) — *biggest win*

**Goal:** Cut 1.8s → 1.0s.

**Work:**
- `storage.py:load_dataset_df(use_polars)` → `pl.scan_csv(..., infer_schema_length=10000, null_values=["","NA"]).collect(streaming=True)` + fallback `pd.read_csv(chunksize=100k)`; parquet cache read when `data.parquet` exists & `rows>100k`
- `profiling.py:71-170` → 
  - `null_summary = df.isna().sum().to_dict()` (one pass)
  - `numeric_cols = df.select_dtypes...` once
  - `nunique` via `pl.n_unique()` or `pd` hash chunked; `exact = rows<=1_000_000`
  - `value_counts` only top 5, only for `categorical_columns` with `unique < 1000`
  - `duplicated` skip if `rows>1M` or `cols>20`, else hash sample
  - `describe` only numeric cols, already limited to 20, now only 8 stats

**Files:** `backend/app/core/storage.py`, `backend/app/core/profiling.py`, `backend/tests/test_profiling*.py` (add `test_profile_vectorized` )

**Validation gate:**
```bash
USE_POLARS=true python scripts/bench_profile.py --rows 1000000 --json | grep -E "profile_ms.*[0-3][0-9][0-9]" # <400 -> <250
USE_POLARS=false python scripts/bench_profile.py --rows 1000000 --json  # <800
PYTHONPATH=backend /tmp/venv09/bin/python -m pytest backend/tests/test_profiling.py backend/tests/test_performance.py -q
# Must keep USE_POLARS=false <1.8s
```

**Risk:** Polars `streaming` flag — pin `polars==1.10.*`, guard `TypeError: unexpected keyword`.

---

### BF-03 — Cache: Chat + Preview + SWR (1d)

**Goal:** Chat repeat 85ms → <5ms HIT, profile HIT stays <10ms, add observability.

**Work:**
- `cache.py:55-78` add `chat:{dataset_id}:{qhash}:{version}` 60s, `preview:{id}:{version}:5k`
- `datasets.py:208-223` add `X-Profile-Ms`, `X-Read-Ms`, `X-Cache: HIT/MISS/STALE`; `profile_dataframe` already caches `profile:{id}:{version}` but wire `version` from `storage`
- `chat` service: before planner, check `cache.get(chat_key)` → return cached `result` + `X-Cache: HIT` 202→200 fast path; after executor set
- Add `stale-while-revalidate`: if `age>60 && age<90` return `STALE` + background recompute via `asyncio.create_task`

**Files:** `backend/app/core/cache.py`, `backend/app/api/datasets.py`, `backend/app/services/chat_service.py`

**Validation gate:**
```bash
curl -i http://localhost:8000/api/datasets/<id> | grep X-Cache  # MISS then HIT <10ms
curl -i http://localhost:8000/api/chat -X POST -d '{"dataset_id":"<id>","query":"sum Sales"}' | grep X-Cache
PYTHONPATH=backend /tmp/venv09/bin/python -m pytest backend/tests/test_performance.py::test_cache_hit_lt_10ms -q
```

---

### BF-04 — Storage I/O: Single-Pass + Parquet + Index (1.5d)

**Goal:** Upload 3.2s → <2s, re-read 120ms → 40ms.

**Work:**
- `datasets.py:81-99` upload: keep `NamedTemporaryFile`, then single `pl.scan_csv(tmp).collect()` → `df_preview = df.head(5000).to_pandas()` → `profile = profile_dataframe(df, ...)` → `df.write_parquet(data.parquet)` + `df.write_csv(data.csv)` in same `collect` (or `df.to_pandas().to_csv` chunks)
- `storage.py:load_dataset_df` read `data.parquet` first if exists, else `scan_csv`/`read_csv`
- `storage.py:list_datasets` add `pg_trgm` `GIN` index when `DATABASE_URL` postgres: `CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE INDEX CONCURRENTLY ... USING GIN (original_filename gin_trgm_ops)`; FS fallback keeps `ilike` scan but adds `lru_cache` 100 items for `list_datasets(q)` 5s

**Files:** `backend/app/api/datasets.py`, `backend/app/core/storage.py`, `backend/app/core/db.py` (migration)

**Validation gate:**
```bash
time curl -F file=@/tmp/100MB.csv http://localhost:8000/api/datasets/upload  # <2s
docker stats --no-stream | grep backend  # MEM <300MB during upload
python scripts/bench_read.py --rows 1000000  # parquet 40ms vs csv 120ms
```

---

### BF-05 — Frontend: Trim + Cache + Pagination (1d)

**Goal:** Preview TTI 400ms → <180ms, payload 120KB → 32KB.

**Work:**
- `streamlit_app.py:671-688` trim `describe` to 8 keys before `st.json` (or send `describe_numeric` only), paginate `columns` expander 20 per page, `st.cache_data(ttl=60)` on `get_dataset_details` + `list_datasets`
- Use `orjson` for `json.dumps` if available
- Add `st.skeleton` (Streamlit 1.39 `st.spinner` already) + `st.toast` already; keep no extra dep

**Files:** `frontend/streamlit_app.py`, `frontend/requirements.txt` (optional `orjson`)

**Validation gate:**
```bash
curl -s http://localhost:8000/api/datasets/<id> | python -c "import json,sys; d=json.load(sys.stdin); print(len(json.dumps(d['profile']['describe'])))"  # <10KB
# AppTest timing
PYTHONPATH=backend /tmp/venv09/bin/python -m pytest frontend/tests -q  # if exists, else AppTest manual
```

---

### BF-06 — Scale: Queue, Concurrency, p95 (1.5d)

**Goal:** p95 85ms → <60ms Redis / <100ms FS at 50 users, 100 users <150ms.

**Work:**
- `app/main.py` add `asyncio.Semaphore(20)` middleware for chat, `X-Concurrency` header
- Keep Celery 202 for `forecast` >1M, add `GET /api/jobs/{id}` already polls
- `locustfile.py` extend to 100 users, add `bench_chat.py` with cache hit run
- OTEL `X-Profile-Ms` to `trace` span, `Sentry` transaction for `profile`
- Add `scripts/bench_locust_parse.py` to assert `p95 <150` from `locust --csv`

**Files:** `backend/app/main.py`, `locustfile.py`, `scripts/bench_locust_parse.py`, `BENCHMARKS.md`

**Validation gate:**
```bash
locust --headless -u 50 -r 10 --run-time 30s -H http://localhost:8000 --csv /tmp/locust && cat /tmp/locust_stats.csv | python scripts/bench_locust_parse.py --p95 150
locust --headless -u 100 -r 20 --run-time 30s -H http://localhost:8000 --csv /tmp/locust100  # p95 <150
```

---

### Final Docs (1d, parallel to BF-06)

- Commit `BENCHMARKS.json` + `BENCHMARKS.md` with **before/after** per level (6 rows + overall)
- Update `ARCHITECTURE.md` Data Engine section, `COMPARISON.md` 10M cell (1.8s→0.85s)
- Add `plan/blazfast/07_migration.md` rollback steps

**Total:** 8d eng + 1d docs = **9d** calendar (BF-01→BF-03 can run 3d, BF-04→BF-06 next 4d).

## Ordering Rules

- Never start BF-N+1 until BF-N gate `grep` passes and `pytest -q` green on that slice (keep `USE_POLARS=false` green).
- Each level is a separate commit; do not squash until final tag.

## Non-goals per level

- BF-01: no code perf, only harness.
- BF-02: no cache changes.
- BF-03: no storage double-read fix (that’s BF-04).
- BF-04: no frontend changes.
- BF-05: no DB index changes.
- BF-06: no new features, only load & observability.
