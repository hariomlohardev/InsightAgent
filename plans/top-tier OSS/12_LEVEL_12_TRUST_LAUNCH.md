# Level 12 — Trust & Launch: 9.0 → 9.5 (The “Why Trust Us” Gate)

> **From “looks good” to “proven, published, trusted for 100k rows in prod”.**

## Goal

Earn trust with numbers and shine, then tag `v1.0` and launch to HN/Product Hunt with a demo that doesn’t 500 on p50.

## Success Criteria

- [ ] `ruff` + `black` + `mypy --strict app/core` 0 errors in CI (`pre-commit` + `make lint`), `make cov --cov-fail-under=95` green
- [ ] `SECURITY.md` + `SECURITY_AUDIT.md` (AST `validate_code` + `validate_sql` review, `pip audit`, `npm audit` in `landing`+`docs`+`landing/docs` 0 high)
- [ ] `BENCHMARKS.md` (committed) with `profile 1M <2s, 10M <3s`, `chat groupby <2s`, `p95 locust 50u <300ms`, run on `c5.large` or GitHub runner, steps repro `scripts/bench_*.py`
- [ ] `COMPARISON.md` table vs Metabase / Superset / Tableau / Power BI / PostHog (rows: setup time, SQL needed, LLM, self-host, price, 10M speed) — honest, sourced
- [ ] `README` demo GIF 20s (upload → chat → pin → share), `ARCHITECTURE.md` diagram (Mermaid), `CHANGELOG.md` Keep-a-Changelog, `v1.0` tag + GitHub Release notes + `docker-compose up` one-liner re-tested
- [ ] Launch kit: `LAUNCH.md` (HN Title, first comment, Product Hunt assets), `video 60s` script in `docs/`, `demo.insightagent.com` stable 7d, post-mortem after launch
- [ ] `pytest` 160+ (add security tests), no `py_compile` error, `landing` + `docs` `npm run build` 0 errors

## Context

- L9 gives DB+S3+OTEL, L10 gives speed, L11 gives SDK/docs/demo. 9.0 is buildable; 9.5 is *credible* — numbers, polished surface, no `any` in `core`, and a GIF that sells.
- Current: `make lint` is `py_compile` only; `mypy strict` not run; `coverage` 80 threshold in `Makefile` but not 95; `SECURITY.md` exists but no audit report; `BENCHMARKS.md` is empty; `COMPARISON.md` not exists; no `CHANGELOG`, no `v1.0`.

## Constraints

- Keep OSS MIT; audit is docs, not SOC2.
- `landing` already Vite static; `docs` will be Docusaurus from L11 — reuse.
- `mypy strict` only for `app/core` (not `api` with FastAPI `Any`).

## Key Decisions

| Decision | Recommended | Why |
|----------|-------------|-----|
| Lint gate | `ruff==0.8 + black==24 + mypy==1.11` `pre-commit` | Zero config debate, fast, strict for `core` only |
| Coverage | `pytest --cov=app --cov-report=html --cov-fail-under=95` | Proves 95, not 80 |
| Benchmark | `scripts/bench_profile.py` + `scripts/bench_chat.py` + `locustfile.py` committed numbers | Repro on any runner |
| Comparison | `COMPARISON.md` sourced, not trash-talk | Trust |

## Work Plan

### 12.1 — Lint & Types (1d)
- `.pre-commit-config.yaml`, `pyproject.toml` `tool.ruff`, `tool.black`, `tool.mypy strict core`, `Makefile` `lint: ruff check app/ && mypy app/core && black --check`, `backend/pyproject.toml` (or root)
- `app/core/*.py` fix `Any` → `TypedDict`, `make lint` green

### 12.2 — Security & Coverage (1d)
- `pip audit` + `npm audit` in CI, `SECURITY_AUDIT.md` 1-page (validate_code/validate_sql, CORS, secrets no-log, upload 413/400), `make cov` 95 (add `tests/test_security_hardened.py` 5 more)

### 12.3 — Benchmarks & Comparison (1d)
- `scripts/bench_profile.py` (generate 10M, time profile), `locustfile.py` already, `BENCHMARKS.md` table, `COMPARISON.md` 6-column table

### 12.4 — Polish & Launch (1.5d)
- `README` demo GIF (record 20s, optimize 3MB), `ARCHITECTURE.md` Mermaid, `CHANGELOG.md`, `LAUNCH.md` (HN title options, first comment, PH gallery 5 images), tag `v1.0` `git tag -a v1.0 -m "v1.0 top-tier OSS"` + Release, smoke `docker-compose up` + e2e 15 queries again

**Total 4.5d**

## Validation Plan

| Check | Command | Expected |
|-------|---------|----------|
| Lint | `make lint` | 0 errors |
| Types | `mypy --strict app/core` (or `mypy app/core --ignore-missing-imports`) | 0 |
| Coverage | `make cov` | 95+ line in report |
| Audit | `pip audit; cd landing && npm audit` | 0 high |
| Bench | `python scripts/bench_profile.py --rows 1000000` + `locust --headless -u 50` | numbers in BENCHMARKS.md |
| Build | `cd docs && npm run build && cd ../landing && npm run build` | 0 errors |
| Regression | `pytest -q` | 160+ |
| Manual | `docker-compose up` + 20s GIF flow | share link works for incognito |

## Risks / Rollback

- `mypy strict` on `core` fails many lines → fix `core` only, `api` stays normal; rollback: lower to `mypy app/core --ignore-missing-imports` with per-file ignores.
- `coverage 95` fails due to `cloud` mock branches → add `pragma: no cover` for `if stripe not installed` graceful fallbacks, or add tests until 95.
- Benchmark numbers worse on CI runner → doc runner spec, commit `c5.large` numbers, note “on GitHub runner X”.

## Open Questions

- None. Stack `ruff/black/mypy/pip-audit/locust` proven at top OSS (PostHog, Metabase).
