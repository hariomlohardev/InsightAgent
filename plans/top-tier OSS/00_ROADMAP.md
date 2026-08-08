# Top-Tier OSS — From 7.5 → 9.5

> **Current:** 7.5/10 OSS MVP (138 tests, heuristic+LLM, connectors, analytics, automation, enterprise RBAC+queue+S3, cloud workspaces/billing). Self-host works, but filesystem-only, no Postgres, no OTEL, coverage not 95%, Streamlit limits white-label, docs/community thin, 10M not proven.
>
> **Goal:** 9.5/10 top-tier OSS that stands next to Metabase / Supabase / PostHog — `docker-compose up` in 30s, `README` demo GIF, `CONTRIBUTING` 5min to PR, `make cov` 95%, `mypy strict` clean, p95 <300ms at 50 users, 10M CSV <2s, Postgres+S3 prod, plugin SDK, docs site, live sandbox.

## Ladder (pick one by one, each ends green)

| Level | Name | Outcome | Rating delta |
|-------|------|---------|--------------|
| **09** | **Data & Storage Foundation** | Postgres + Alembic (fs fallback), `storage` → DB migration, S3/MinIO prod, backups, OTEL + Sentry | 7.5 → 8.0 |
| **10** | **Performance & Scale** | Polars+ DuckDB 10M <2s proven, Redis hit <10ms, async streaming upload, pgvector search, load `locust 50u` p95 | 8.0 → 8.5 |
| **11** | **DX & Community** | `CONTRIBUTING.md`, SDK `pip install insightagent`, plugin API, Docusaurus docs, demo sandbox `demo.insightagent.com`, issue/PR templates | 8.5 → 9.0 |
| **12** | **Trust & Launch** | `mypy strict` + `ruff+black` CI gate 0 errors, coverage 95%, security audit report, benchmark vs Metabase/Superset, HN video, `v1.0` tag | 9.0 → 9.5 |

Each level is **self-contained** — merge, tag `v0.9`, `v0.10`… `v1.0`, deploy, then pick next. No level breaks `docker-compose up` without its deps (graceful fallback).

## How to pick

```bash
# 09 first (required for all later)
cat "plans/top-tier OSS/09_LEVEL_09_DATA_FOUNDATION.md"`
# Approve → build → pytest -q + docker-compose up
# then 10, 11, 12 sequentially
```

## Success at 9.5

- `docker-compose up` 30s → upload 1M CSV → chat → pin → share link works for stranger with no key.
- `make cov` 95%, `make lint` 0, `mypy --strict app/core` 0, `locust -u 50 p95 <300ms` posted to `BENCHMARKS.md`.
- `docs/` deploys to `docs.insightagent.com`, `CONTRIBUTING.md` → PR in 5min, SDK `from insightagent import chat`.
- Demo GIF in README, comparison table vs Metabase/Superset/Tableau, `v1.0` HN launch >200 stars week 1.

## Constraints

- Keep MIT + `CLOUD=false` frictionless (same flag model as L7/L8). Postgres when `DATABASE_URL` set else filesystem.
- No rewrite — additive `cloud/` already, now additive `core/db.py`, `sdk/`, `docs/`.
- All levels keep `pytest -q` 100+ passing before merge.

## Map to existing

- L1-L8 delivered the product. Top-tier levels harden it to *community-operable* production OSS.
