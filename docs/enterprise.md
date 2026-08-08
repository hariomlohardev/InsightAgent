# Enterprise Guide — Level 7

InsightAgent is **MIT + open-core**: self-host without `AUTH_REQUIRED` stays frictionless (anon editor). Flip flags for enterprise:

## Flags

| Flag | Default | Effect |
|------|---------|--------|
| `AUTH_REQUIRED` | `false` | When `true`, all `POST/DELETE` need `Bearer` or `X-API-Key` |
| `ENTERPRISE` | `false` | Alias for auth required (paid hosting) |
| `JWT_SECRET` | auto | Random hex saved to `storage/jwt_secret` on first run |
| `JWT_EXP_HOURS` | `24` | Token lifetime |
| `REDIS_URL` | unset | `redis://redis:6379/0` enables cache (60s) + queue (202) |
| `CACHE_TTL` | `60` | Seconds |
| `USE_POLARS` | `false` | `true` → `pl.read_csv` for large files |
| `STORAGE_BACKEND` | `fs` | `s3` via `fsspec` + `S3_BUCKET` |

## Run Modes

```bash
# OSS (default) — no auth/redis needed
docker-compose up

# Enterprise (auth + redis + worker)
cp .env.example .env
# set JWT_SECRET=$(openssl rand -hex 32) and AUTH_REQUIRED=true
docker-compose --profile prod up   # adds redis + worker

# Prod 3-service
docker-compose -f docker-compose.prod.yml up
```

All runs work without redis — queue falls back to sync, cache falls back to in-memory LRU.

## Auth & RBAC

- `POST /api/auth/register {email,pass,role=viewer}` → 201; first admin seeded `admin@local / admin`
- `POST /api/auth/login → {access_token}` → use `Authorization: Bearer <token>` or `X-API-Key`
- `POST /api/auth/api-key {name,scopes}` (editor/admin) → raw key once
- Roles: `admin` (all), `editor` (create/edit), `viewer` (read-only). `GET /api/auth/me` returns role.

Viewer blocked test: `curl -H "Authorization: Bearer $VIEWER" -F file=@sales.csv http://localhost:8000/api/datasets/upload` → 403.

## Audit

Append-only `storage/audit/YYYY-MM-DD.jsonl`, rotated (30d). `GET /api/audit` (admin only) → last 100.

## Performance

- Polars optional: `USE_POLARS=true` + >1M rows → 10x faster. `backend/tests/test_enterprise.py::test_cache_and_polars_optional` covers fallback.
- Redis cache: `profile:{dataset}:{version}` + `chat:{id}:{hash}` with `CACHE_TTL=60`
- Queue: `forecast` or >1M rows with `REDIS_URL` → `POST /api/chat` returns `202 {job_id}` → `GET /api/jobs/{id}` polls `storage/jobs/{id}.json`

## Storage Backend

`STORAGE_BACKEND=s3` + `S3_BUCKET=mybucket` + `AWS_*` (or MinIO `S3_ENDPOINT`). Falls back to `fs` if `fsspec` missing.

## Frontend

When `AUTH_REQUIRED=true`, Streamlit sidebar shows **Login** (email/pass → token in `st.session_state["token"]`), **Logout**, **API Keys** (admin), **Audit** tab (admin lists last 100). Viewers hide Delete/Share. Chat shows “Job queued… poll” when 202.

## Quality Gates

```bash
make cov   # pytest --cov=app --cov-fail-under=80
make lint  # ruff + black --check
pytest -q  # 131 passed
```
