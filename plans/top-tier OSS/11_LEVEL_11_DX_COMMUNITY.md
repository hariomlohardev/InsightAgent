# Level 11 — DX & Community: 5min to First PR (8.5 → 9.0)

> **From “works for me” to “works for 1,000 contributors”.**

## Goal

Make a stranger go from `README` → `PR` in 5min, and `pip install insightagent` → `chat(df, "top 5")` in 2 lines.

## Success Criteria

- [ ] `CONTRIBUTING.md` (setup, `make install`, `make test`, `make lint`, how to add connector), `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE` MIT, `GOVERNANCE.md`, `.github/ISSUE_TEMPLATE/bug_report.md` + `feature_request.md`, `PULL_REQUEST_TEMPLATE.md`, `CODEOWNERS`
- [ ] SDK: `sdk/` or `packages/python/insightagent/` with `pip install insightagent` (`pyproject.toml`) → `from insightagent import InsightAgent; agent.chat(df, "forecast Sales")` wraps `httpx` to local or cloud `BACKEND_URL`
- [ ] Plugin API: `app/plugins/` `BaseConnector` + `BaseAnalyzer` entry points (`insightagent.connectors` via `importlib.metadata`), example `my_connector.py` in `examples/`
- [ ] Docs site: `docs/` (Docusaurus or Mintlify) `npm run build` deploys to `docs.insightagent.com` (or GitHub Pages), MDX from `README` + `CLOUD.md` + `ARCHITECTURE.md`, search
- [ ] Demo sandbox: `demo.insightagent.com` (or `demo/` branch) with read-only `sample_data/sales.csv` and `?demo=1` flag (no upload, no auth)
- [ ] `pytest` 155+ (sdk tests 5), `npm run build` in `docs/` 0 errors, `make install` 30s on fresh clone

## Context

- `README.md` already 200 lines but no `CONTRIBUTING`; `frontend/` has no SDK; `app/core/connectors.py` is closed (no entry points); `docs/` has `enterprise.md`/`CLOUD.md` but no site; no demo.
- `backend/requirements.txt` + `frontend/requirements.txt` exist, but `make install` not timed.
- Tests 138; ten marketplace templates prove plugin need.

## Constraints

- Keep Streamlit for app; docs can be Node (Docusaurus) separate, not in backend `up`.
- SDK must work with `CLOUD=false` (local) and `CLOUD=true` (cloud) via `INSIGHTAGENT_URL` env.
- No breaking of `docker-compose up`.

## Key Decisions

| Decision | Recommended | Why |
|----------|-------------|-----|
| Docs | `Docusaurus 3` classic | Markdown reuse, search built-in, GitHub Pages 1-click | `Mintlify` closed |
| SDK | `sdk/pyproject.toml` `insightagent` | `pip install -e sdk` for contributors, publish to PyPI later | `frontend` SDK not needed |
| Plugins | `importlib.metadata entry_points` | No new dep, pip installable | |
| Demo | `?demo=1` read-only mode + `sample_data` seeded, `AUTH_REQUIRED=false`, `CLOUD=false` but header “Demo” | No DB needed |

## Work Plan

### 11.1 — Community Files (0.5d)
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `.github/ISSUE_TEMPLATE/*`, `PULL_REQUEST_TEMPLATE.md`, `CODEOWNERS`, `LICENSE` check

### 11.2 — SDK (1.5d)
- `sdk/pyproject.toml`, `sdk/insightagent/__init__.py` (`Client`, `chat`, `upload`, `dashboard`), `sdk/tests/test_sdk_mock.py` (httpx mock)

### 11.3 — Plugin API (1d)
- `app/plugins/__init__.py` (`BaseConnector`, `register_connector`), `app/core/connectors.py` loads entry points, `examples/my_connector.py`

### 11.4 — Docs Site + Demo (1.5d)
- `docs/` Docusaurus `docusaurus.config.js`, import `README`, `ARCHITECTURE.md`, `CLOUD.md`, `BENCHMARKS.md`, `npm run build`
- `frontend/streamlit_app.py` `if ?demo=1: disable upload/delete, show banner`, `docker-compose.demo.yml`

**Total 4.5d**

## Validation Plan

| Check | Command | Expected |
|-------|---------|----------|
| Contributing | `cat CONTRIBUTING.md \| head` | `make install` 3 steps |
| SDK | `pip install -e sdk && python -c "from insightagent import InsightAgent; print(InsightAgent)"` | import ok |
| Plugin | `pytest sdk/tests/test_sdk_mock.py -v` | 2 passed |
| Docs | `cd docs && npm run build` | 0 errors, `build/` exists |
| Demo | `streamlit run frontend/streamlit_app.py -- --demo` manual | banner, no delete |
| Regression | `pytest -q` | 155+ |

## Risks

- Docs Node adds 300MB `node_modules` if committed → `.gitignore` it, CI `npm ci`.
- SDK name `insightagent` taken on PyPI → `insight-agent` fallback, keep import `insightagent`.

## Open Questions

- Docs host: GitHub Pages vs Vercel? Default GitHub Pages (free).
