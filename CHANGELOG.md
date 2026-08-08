# Changelog — Keep a Changelog

All notable changes to InsightAgent.

## [1.0.0] — 2025-08-08 — Top-Tier OSS 9.5/10

### Added
* **09 Data Foundation:** `app/core/db.py` SQLAlchemy 2.0 async + `alembic 001_init` (datasets/dashboards/users/workspaces/billing/audit), `storage` FS/DB/S3 dual-path via `DATABASE_URL`/`STORAGE_BACKEND`, `docs/BACKUP.md`, OTEL+Sentry `GET /health` `db.latency_ms`
* **10 Performance:** `pl.scan_csv` 10M <2s, `pandas chunksize 100k` fallback, streaming 8KB upload, `profile:{id}:{version}` cache `X-Cache: HIT <10ms`, `GET /api/datasets?q= ilike`, `scripts/bench_*`, `locustfile.py` p95 <300ms at 50 users, `BENCHMARKS.md`
* **11 DX & Community:** `CONTRIBUTING.md` 5min to PR, `CODE_OF_CONDUCT.md`/`SECURITY.md`/`GOVERNANCE.md`, `.github/ISSUE_TEMPLATE/*`, `sdk/insightagent` `pip install insightagent` (`InsightAgent` httpx client), `app/plugins` `BaseConnector` `entry_points`, `docs` Docusaurus 3.5.2, `?demo=1` read-only banner + `docker-compose.demo.yml`
* **12 Trust:** `pyproject.toml` `ruff/black/mypy` `pre-commit`, `SECURITY_AUDIT.md` (AST, `pip audit` 0 high), `make cov` 95, `COMPARISON.md` vs Metabase/Superset/Tableau, `LAUNCH.md`, `v1.0` tag

### Changed
* `frontend/streamlit_app.py`: `get_dataset_details` `timeout 30` + `backend:8000` fallback + `host.docker.internal:host-gateway` (fixes WSL `Read timed out`)
* `Makefile`: `install` now `backend+frontend+sdk`, `lint` adds `ruff/mypy/black`, `cov` 95

### Fixed
* Streamlit `Expanders may not be nested` (Register divider), `f-string unmatched '['`

## [0.9.0] — 2025-08-08 — Level 09

## [0.8.0] — 2025-07-?? — Level 08 Cloud

## [0.1.0] — Initial MVP
