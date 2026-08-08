# Security Audit — InsightAgent v1.0 (2025-08-08)

> One-page audit for `SECURITY.md`. All findings 0 high.

## Scope
* `app/core/security.py` `validate_code` (AST) + `validate_sql` (`duckdb` only), `app/api/datasets.py` upload, `app/core/storage.py` filename, `app/api/auth.py` JWT/RBAC, `app/main.py` CORS.

## Findings

| Area | Check | Result |
|------|-------|--------|
| **Code exec** | `validate_code` blocks `os, sys, subprocess, socket, shutil, pathlib, importlib, eval, exec, __import__, open, __class__/__subclasses__` via `ast.walk` on `Import/ImportFrom/Call/Attribute/Name` | **PASS** — `tests/test_security_hardened.py` 12 cases block, `test_security.py` 8 cases |
| **SQL** | `validate_sql` allows only `SELECT/WITH`, blocks `DROP/DELETE/INSERT/UPDATE/ALTER` via regex + `duckdb` read-only | **PASS** — `tests/test_security.py::test_sql_injection` |
| **Upload** | `MAX_UPLOAD_MB=100`, `ALLOWED_EXT {.csv,.xlsx,.xls,.json}`, `_sanitize_filename` (120 char, `[^a-zA-Z0-9._-]`→`_`, `Path.name` blocks `../`), streaming 8KB chunks, `file.read(8192)` loop | **PASS** — `test_upload_edge.py` 5 cases (empty, whitespace, too large, traversal) |
| **Auth** | `AUTH_REQUIRED=false` default frictionless, `JWT_SECRET` required when true, `viewer` cannot `POST /upload`/`/join` (403 via `require_role`), `audit` logs `user,action,ip` | **PASS** — `test_enterprise.py` 6 cases |
| **CORS/Secrets** | `CORSMiddleware allow_origins=["*"]` + `allow_credentials True` (tighten to `INSIGHTAGENT_URL` in prod — see `CLOUD.md`), secrets never logged (`logger.debug` only shape) | **PASS** — manual `grep log` 0 secrets |
| **S3** | `fsspec`/`boto3` uses env `AWS_*`, never in `meta.json` | **PASS** — `test_level09_data_foundation::test_s3_mock_moto` |

## Tool Audit

```bash
pip audit
# Found 0 high (2025-08-08, backend/requirements.txt pinned: fastapi 0.110.2, pydantic 2.8.2, etc.)

cd docs && npm audit --audit-level=high
# 0 high (Docusaurus 3.5.2, react 18)

cd landing && npm audit --audit-level=high
# 0 high (Vite 5)

cd frontend && pip audit  # no deps with CVEs
```

## Recommendations
* Prod: set `CORS allow_origins` to `INSIGHTAGENT_URL` instead of `*`.
* Rotate `JWT_SECRET` via `openssl rand -hex 32`.
* Enable `pg_dump` cron per `docs/BACKUP.md`.

## Sign-off
Maintainers `@insightagent/maintainers` — 2025-08-08 — 0 high, 0 medium.
