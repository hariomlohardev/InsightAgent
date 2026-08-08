# Level 09 — Data & Storage Foundation: Postgres + S3 + OTEL (7.5 → 8.0)

> **From filesystem that works to DB that scales with 100 tenants and survives restart.**

## Goal

Replace implicit filesystem-only with **explicit Postgres+S3 prod path** while keeping `docker-compose up` filesystem-fast for contributors. Add observability so 500 errors stop being invisible.

## Success Criteria

- [ ] `DATABASE_URL=postgresql://...` → `app/core/db.py` uses SQLAlchemy async + Alembic; else filesystem fallback (contributor `up` still works, no DB needed)
- [ ] Migration `alembic revision --autogenerate` creates `datasets`, `dashboards`, `users`, `workspaces`, `billing` tables; `storage.py` reads via `get_storage_path()` when `CLOUD=false` else `DATABASE_URL` when set
- [ ] S3/MinIO via `fsspec/s3fs` for `datasets/{id}/data.csv` when `STORAGE_BACKEND=s3` (prove with `moto` mock, not real AWS)
- [ ] Backups: `pg_dump` cron + `storage/workspaces/{ws_id}/` tar docs in `docs/BACKUP.md`
- [ ] OTEL: `app/main.py` adds `OTEL_EXPORTER_OTLP_ENDPOINT` (fallback no-op), Sentry DSN optional, `GET /health` adds `db` latency
- [ ] `pytest` 145+ (add 7), `py_compile` clean, `docker-compose up` without `DATABASE_URL` still 138 green, with `DATABASE_URL` also green

## Context & Current Facts

- `storage.py` 536 lines, `_atomic_write_json` + `get_storage_path()` ContextVar per workspace; `_datasets_dir()` etc. No DB, no transactions, concurrent writes risk torn JSON.
- `config.py` `is_cloud()` + `get_workspace_id()` ContextVar already; easy to add `DATABASE_URL`.
- `docker-compose.yml` has `backend+frontend+redis+worker` (prod profile); no `postgres` yet. `requirements.txt` has `fsspec/s3fs` but not `sqlalchemy/alembic/psycopg`.
- Tests 138, filesystem only; no DB fixture.

## Constraints & Non-Goals

- Keep `CLOUD=false` + no `DATABASE_URL` → pure filesystem (no migration for contributor).
- No multi-region, no read replica (L10).
- No data warehouse federation beyond existing DuckDB `join`.

## Key Decisions

| Decision | Recommended | Why | Alt rejected |
|----------|-------------|-----|--------------|
| DB | `SQLAlchemy 2.0 async + asyncpg + Alembic` | Standard, async fits FastAPI, migration auto, psycopg fallback for sync scripts | `Tortoise/SQLModel` smaller ecosystem |
| Fallback | `if DATABASE_URL else filesystem` branch in `storage.py` + `core/db.py` helper `use_db()` | One code path, contributors no DB | Forcing Postgres breaks OSS DX |
| S3 | keep `fsspec` already in `storage.load_dataset_df` + add `save_dataset` S3 path | Reuses L7 code | `boto3` only → AWS lock-in |
| Observability | `opentelemetry-sdk + fastapi-instrumentor` no-op when endpoint empty, `sentry-sdk` optional | 5MB, no cost when disabled | Vendor OTEL |

## Recommended Approach

Add `backend/app/core/db.py` (`engine`, `sessionmaker`, `Base`, `get_session`), Alembic `backend/alembic/`, tables matching current JSON shape (id TEXT PK, workspace_id, meta JSONB). `storage.py` top: `if use_db(): return db.list_datasets()` else existing. Keep JSON schema identical so tests compare equal.

## Work Plan

### 09.1 — DB Setup (1.5d)
- `app/core/db.py`, `alembic.ini`, `alembic/env.py`, `versions/001_init.py` (datasets, dashboards, users, workspaces, billing, audit)
- `requirements.txt` + `psycopg[binary]==3.1`, `sqlalchemy==2.0`, `alembic==1.13`

### 09.2 — Storage Dual Path (1.5d)
- `storage.py` `use_db()`, `list_datasets()`, `save_dataset()`, `get_dataset_meta()` branches; `conftest.py` fixture `db_session` with `moto`/`test postgres` (sqlite `aiosqlite` for CI)

### 09.3 — S3 Prod + Backup Docs (0.5d)
- `save_dataset` S3 write when `STORAGE_BACKEND=s3`, `docs/BACKUP.md`, `docker-compose.yml` add `postgres:16-alpine` profile `db`

### 09.4 — OTEL (0.5d)
- `main.py` `FastAPIInstrumentor`, `GET /health` adds `db_ms`, `sentry_sdk.init` when `SENTRY_DSN`

**Total 4d**

## Validation Plan

| Check | Command | Expected |
|-------|---------|----------|
| FS still | `DATABASE_URL="" pytest -q` | 138 passed |
| DB | `DATABASE_URL=sqlite+aiosqlite:///./test.db pytest tests/test_storage_db.py -v` | 7 passed (CRUD) |
| S3 mock | `pytest tests/test_storage_s3_mock.py -v` | pass with moto |
| OTEL | `OTEL_EXPORTER_OTLP_ENDPOINT="" pytest -q` | no crash, `/health` has `db` |
| Compose | `docker compose config` | postgres service under profile `db` |

## Risks / Rollback

- DB migration fails → `use_db()` returns False, filesystem stays; rollback: unset `DATABASE_URL`.
- `asyncpg` missing on contributor → `pip install` optional, `use_db()` false when import fails.

## Open Questions

- None. `sqlalchemy` chosen, filesystem fallback proven.
