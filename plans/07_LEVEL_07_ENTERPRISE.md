# Level 7 — Enterprise Hardening: Scale, Security, Quality (OSS + Paid SSO)

> **From "works for me" to "works for 1,000 users with 100M rows."**

---

## Goal

Make the product **enterprise-ready** without forking OSS. After Level 7, you can handle **10M-row CSVs in <3s**, **1k concurrent users**, **audit logs**, **API keys + RBAC**, and **90% test coverage**, with **self-host OSS** staying MIT and **SSO/RBAC** behind `ENTERPRISE=true` flag (paid hosting unlocks it).

## Success Criteria

- [ ] **Auth:** `POST /api/auth/login` (email/pass, `JWT`), `GET /api/auth/me`, `POST /api/auth/api-key` (scoped `read|write`), middleware checks `Authorization: Bearer` for all `POST/DELETE` (GET share links remain public); `anon` still works when `AUTH_REQUIRED=false` (default for OSS)
- [ ] **RBAC:** `admin` (all), `editor` (create/edit datasets/dashboards), `viewer` (read-only); enforced in `api/*` via `Depends(get_current_user)` + `require_role`; `tests/test_rbac.py` proves `viewer` cannot `POST /api/datasets/upload`
- [ ] **Audit Log:** Every `POST/DELETE/PATCH` writes `storage/audit/{YYYY-MM-DD}.jsonl` with `{at, user, action, dataset_id, dashboard_id, ip}`; `GET /api/audit?dataset_id=` returns last 100 (admin only)
- [ ] **Performance:** 10M-row CSV (generated) `profile` <3s, `chat` (groupby) <2s, `dashboard refresh` <1s per widget (measured by `pytest --benchmark`); `DuckDB` + `Polars` (optional) + `Redis` cache for `profile` and `result` (60s TTL)
- [ ] **Queue:** Long queries (>5s) run via `Celery` + `Redis` (or `RQ`) with `POST /api/chat` returning `202 {job_id}` + polling `GET /api/jobs/{id}`; short queries stay sync (no regression)
- [ ] **Scale:** `storage` abstracted to `S3`/`MinIO` when `STORAGE_BACKEND=s3`, else filesystem; `docker-compose.yml` adds `redis` + `worker` services, but `docker-compose up` without them still works (queue disabled)
- [ ] **Quality:** Coverage 90%+ (`pytest --cov=app`), `ruff`/`black` enforced in CI, `mypy` strict for `app/core`, load test `locust` with 50 concurrent users (p95 <500ms for `GET /api/datasets`)
- [ ] `pytest` 90+ tests (add 10), `py_compile` clean, `README` adds "Enterprise" section, `docker-compose.prod.yml` for 3-service deploy

## Context & Current Facts

**L6 delivered:**
- Automation (schedules, Slack, comments, reports), 80+ tests, filesystem dashboards, APScheduler, reportlab.

**Pain:** OSS works for 1 user, 24 rows. Enterprise wants 100 users, 100M rows, SSO, audit, and "Will it be slow?".

## Constraints & Non-Goals

**Constraints:**
- Keep OSS MIT — enterprise flags are **additive**, not subtractive (viewer can still use OSS without auth)
- Keep `docker-compose up` working without `redis`/`postgres` (graceful fallback)
- No vendor lock-in — `S3` is optional, not required

**Non-Goals (for L7):**
- No multi-tenant billing (L8)
- No white-label theming (L8)
- No WAF/CDN (deploy handles)

## Key Decisions

| Decision | Recommended | Why |
|----------|-------------|-----|
| **Auth** | `JWT` (`python-jose` + `passlib[bcrypt]`) + `API keys` (`secrets.token_urlsafe`, hashed in `storage/users/{id}.json`); `AUTH_REQUIRED=false` default so OSS `curl` without token still works; `ENTERPRISE=true` flips to required | Alt: `Auth0` lock-in, `OAuth` alone needs UI; JWT + API keys covers bot + human, flag keeps OSS frictionless |
| **RBAC** | 3 roles in `users/{id}.json` (`role: admin|editor|viewer`), `require_role` decorator checks `current_user.role` | Alt: ABAC (per-dataset ACL) is heavier; 3 roles cover 90% of enterprise needs |
| **Audit** | Append-only `storage/audit/YYYY-MM-DD.jsonl` (one line per action), `GET /api/audit` reads last 100 lines | Alt: DB table adds ops; file is simple, grep-friendly, works without DB |
| **Perf: Polars** | Add `polars==1.10.0` as **optional** engine: if `USE_POLARS=true` and `df.shape[0] > 1M`, use `pl.read_csv` + `df.group_by` else pandas; keep `pandas` as default for compat | Alt: full Polars migration breaks existing `coder` templates; optional is safe, 10x faster for >1M |
| **Cache** | `Redis` (`redis==5.0`) with `CACHE_TTL=60` for `profile` + `result` keyed by `dataset_id+version+query_hash`; if `REDIS_URL` not set, in-memory `lru_cache` fallback | Alt: no cache is slow for repeated dashboards; Redis is 5MB image, optional |
| **Queue** | `Celery` + `Redis` (`celery==5.3`, `redis`) with `task_serializer=json`, `POST /api/chat` checks `estimated_rows > 1M` or `query contains forecast` → `delay` and return `202`, else sync | Alt: `RQ` simpler but Celery is standard; keep sync for small queries to avoid extra hop |
| **Storage backend** | `fsspec` abstraction (`s3fs` for `s3://bucket`) behind `storage.py` `STORAGE_BACKEND=fs|s3`; if `s3`, `datasets/{id}/data.csv` → `s3://bucket/datasets/{id}/data.csv` | Alt: direct `boto3` ties to AWS; `fsspec` supports S3/MinIO/GCS |
| **Frontend** | Streamlit: add `Login` page (email/pass) when `AUTH_REQUIRED=true`, hide `Delete` for viewers, show `Audit` tab for admin | Alt: Next.js auth is heavier; Streamlit `st.session_state["token"]` works for L7 |

## Recommended Approach

Add **three pillars**: **Auth/RBAC/Audit**, **Perf/Cache/Queue**, **Quality**.

Keep all behind flags so `docker-compose up` without env still boots OSS.

### Data Flow

```
Request → Auth middleware (if AUTH_REQUIRED) → RBAC check → Audit log → Handler
Chat (small) → executor sync → result
Chat (large) → Celery delay → job_id → poll → result (cached in Redis)
Profile → Redis cache (60s) → pandas or polars → storage (fs or s3)
```

## Work Plan (Ordered)

### Unit 7.1 — Auth, Users, API Keys (2 days)
**Surfaces:** `backend/app/core/auth.py` (new), `app/api/auth.py` (new), `app/models/user.py`, `app/config.py`, `app/main.py` (middleware)
- [ ] **7.1.1** `core/auth.py`: `hash_password`, `verify`, `create_jwt(user_id, role, exp)`, `decode_jwt`, `create_api_key(user_id)` (store `hashed_key` in `storage/users/{id}.json` + `storage/api_keys/{hashed}.json`)
- [ ] **7.1.2** `api/auth.py`: `POST /api/auth/register` (first user is `admin`), `POST /api/auth/login` → `JWT`, `GET /api/auth/me`, `POST /api/auth/api-key` (admin/editor), `DELETE /api/auth/api-key/{id}`
- [ ] **7.1.3** `config.py`: `AUTH_REQUIRED=false`, `JWT_SECRET=`, `JWT_EXP_HOURS=24`, `ENTERPRISE=false`
- [ ] **7.1.4** Middleware: `Depends(get_current_user)` that checks `Authorization: Bearer ...` or `X-API-Key`, sets `request.state.user`; if `AUTH_REQUIRED=false` and no token, `user=anon (viewer)`; if `true` and no token, 401
- [ ] **7.1.5** Seed `storage/users/admin.json` on first run if not exists (email `admin@local`, pass `admin`, role `admin`) for dev
**Validation:** `pytest tests/test_auth.py` (register, login, me, api-key, anon when not required, 401 when required).

### Unit 7.2 — RBAC & Audit (1.5 days)
**Surfaces:** `backend/app/api/datasets.py`, `dashboards.py`, `schedules.py`, `core/audit.py` (new)
- [ ] **7.2.1** `core/audit.py`: `log(action, user, dataset_id, ip)` → `storage/audit/{date}.jsonl` append; `list_audit(dataset_id?, limit=100)`
- [ ] **7.2.2** Decorator `require_role("editor")` on `POST/DELETE` in datasets/dashboards/schedules/connectors; `GET` is `viewer` ok
- [ ] **7.2.3** `api/audit.py`: `GET /api/audit` (admin only)
- [ ] **7.2.4** Add `user_id` to `datasets.meta.json` (`owner`), `dashboards` (`owner`), for future per-tenant filter (L8)
**Validation:** `pytest tests/test_rbac.py tests/test_audit.py` (viewer blocked, audit written).

### Unit 7.3 — Performance: Polars + DuckDB + Profiling Cache (1.5 days)
**Surfaces:** `backend/app/core/profiling.py`, `app/core/storage.py`, `app/services/connector_service.py`, `requirements.txt`
- [ ] **7.3.1** Add `polars` to `requirements.txt` as optional (`polars==1.10.0`), use `try: import polars` → if `USE_POLARS=true` and `rows>1M`, `pl.scan_csv` + `pl` ops else pandas
- [ ] **7.3.2** Add `Redis` cache: `core/cache.py` (`get`, `set`, `ttl=60`), `CACHE = Redis.from_url(REDIS_URL) if REDIS_URL else InMemoryLRU()`
- [ ] **7.3.3** Cache `profile` (key `profile:{dataset_id}:{version}`) + `chat result` (key `chat:{dataset_id}:{hash(query)}:{version}`) for 60s
- [ ] **7.3.4** Optimize `profile_dataframe` for wide files: sample 20 cols for `describe` if >20
**Validation:** `pytest --benchmark` micro: `profile` 10M rows <3s (or mock), `cache` hit is <10ms.

### Unit 7.4 — Queue: Celery + Redis (2 days)
**Surfaces:** `backend/app/worker.py` (new), `app/api/chat.py`, `app/api/jobs.py` (new), `docker-compose.yml`, `docker-compose.prod.yml`
- [ ] **7.4.1** `worker.py`: `celery = Celery("insight", broker=REDIS_URL, backend=REDIS_URL)`, `@celery.task def run_chat_task(dataset_id, query, user_id)` → `process_query_v2` → store result in `storage/jobs/{job_id}.json` + Redis
- [ ] **7.4.2** `api/chat.py`: if `estimated_rows > 1_000_000` or `forecast` or `REDIS_URL and query len > 500` → `job = run_chat_task.delay(...); return 202 {"job_id", "status":"queued"}` else sync
- [ ] **7.4.3** `api/jobs.py`: `GET /api/jobs/{id}` → `{status, result}` (polling)
- [ ] **7.4.4** `docker-compose.yml` add `redis: image: redis:7-alpine` + `worker: build: ./backend command: celery -A app.worker worker --loglevel=info` both **optional** (`profiles: ["prod"]` so default `up` doesn't need them)
- [ ] **7.4.5** Graceful fallback: if `REDIS_URL` not set, queue disabled, all chat is sync
**Validation:** `pytest tests/test_queue.py` (mock Redis, 202 path, poll).

### Unit 7.5 — Storage Backend: S3/MinIO (1 day)
**Surfaces:** `backend/app/core/storage.py`, `app/config.py`
- [ ] **7.5.1** Add `STORAGE_BACKEND=fs|s3`, `S3_BUCKET`, `S3_ENDPOINT` (MinIO), `AWS_*`; use `fsspec` or `boto3` for `open`/`list`; keep `fs` as default
- [ ] **7.5.2** Test with `moto` mock S3 in `tests/test_storage_s3_mock.py`
**Validation:** `pytest tests/test_storage_s3_mock.py`.

### Unit 7.6 — Frontend: Auth & Audit UI (1 day)
**Surfaces:** `frontend/streamlit_app.py`, `pages/admin.py` (new)
- [ ] **7.6.1** If `AUTH_REQUIRED=true`, show `Login` form (email/pass → `POST /api/auth/login` → store `token` in `st.session_state`), `Logout`, `API Keys` page for admin
- [ ] **7.6.2** Hide `Delete`/`Share` for `viewer`, show `Audit` tab for `admin` (list last 100)
- [ ] **7.6.3** Show `Queue` status in Chat (`Job queued... poll...`) when `202`
**Validation:** Manual: login as viewer → try upload → 403; admin → audit visible.

### Unit 7.7 — Quality: Coverage, Lint, Load (1 day)
**Surfaces:** `Makefile`, `.github/workflows/ci.yml`, `backend/tests/`
- [ ] **7.7.1** `make cov` (`pytest --cov=app --cov-report=html --cov-fail-under=90`), add to CI
- [ ] **7.7.2** `ruff` + `black` + `mypy` (strict for `core/`), CI must pass
- [ ] **7.7.3** `locustfile.py` (50 users, `GET /api/datasets`, `POST /api/chat` small) → `locust --headless -u 50 -r 10 --run-time 30s` shows p95 <500ms
**Validation:** `make cov` shows 90+, `make lint` clean.

### Unit 7.8 — Docs & Release (0.5 day)
- [ ] Tag `v0.7-enterprise`, `docker-compose.prod.yml`, `docs/enterprise.md` (how to run with Redis/S3/SSO)

**Total: ~11 days (3 weeks)**

## Validation Plan

| Check | Command | Expected |
|-------|---------|----------|
| All tests | `pytest tests -q` | 90+ passed |
| Auth | `pytest tests/test_auth.py -v` | register/login/api-key |
| RBAC | `pytest tests/test_rbac.py -v` | viewer 403 on POST |
| Audit | `pytest tests/test_audit.py -v` | log written, list |
| Cache | `pytest tests/test_cache.py -v` | hit <10ms |
| Queue | `pytest tests/test_queue.py -v` | 202 + poll |
| S3 mock | `pytest tests/test_storage_s3_mock.py -v` | pass |
| Coverage | `make cov` | 90%+ |
| Lint | `make lint` | 0 errors |
| Manual | Login viewer/admin, upload 10M-row CSV (or 1M for demo), chat → <2s, dashboard refresh | — |
| Regression | `python /tmp/e2e_15_queries.py` | 15/15 |

**Highest-risk:** Queue + cache adds infra. Mitigate by keeping both **optional** (no Redis → sync, no cache → direct).

## Risks / Rollback

| Risk | Mitigation | Rollback |
|------|------------|----------|
| `JWT` secret not set in OSS → insecure default | Generate random secret on first run, write to `storage/jwt_secret` | Revert to `AUTH_REQUIRED=false` by default |
| `Celery` needs `redis` but user didn't run `docker-compose --profile prod up` → `POST /api/chat` 500 | Guard: if `REDIS_URL` missing, queue disabled, log warning | Keep sync path as default |
| `Polars` not installed → `USE_POLARS` breaks | `try: import polars` → fallback to pandas | Remove `USE_POLARS` flag |
| `S3` mock `moto` adds 100MB | Make `test_storage_s3_mock.py` skip if `moto` not installed | Mark as `pytest.mark.skip` |
| Audit file grows forever | Rotate daily, `max_audit_days=30` cleanup | Delete `storage/audit/` older than 30d |

## Open Questions

- None. `JWT+passlib`, `APScheduler`→`Celery` optional, `Redis` cache, `fsspec` S3 are all MIT, proven.

---

**Approval Gate:** Reply `Approve` to build Level 7, or `Change` to edit.
