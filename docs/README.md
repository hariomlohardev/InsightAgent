# InsightAgent — AI Data Analyst Agent

**Chat with your CSV/Excel/SQL in plain English. Get charts, insights & reports in seconds.**

> Open Source Alternative to Tableau + ChatGPT Code Interpreter + Power BI | Built with Python | **Supports OpenAI, Groq, Gemini, Claude, Ollama**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green) ![Streamlit](https://img.shields.io/badge/Streamlit-1.39-red) ![License](https://img.shields.io/badge/License-MIT-yellow) ![Level](https://img.shields.io/badge/Level-08%20Cloud-orange) ![Tests](https://img.shields.io/badge/tests-138%20passed-brightgreen)

---

## 🚀 What It Does

Upload any CSV/Excel/JSON, connect **Postgres/MySQL/SQLite/BigQuery/Sheets** → Schedule **"Email PDF of Sales by Region every Monday 9am + Slack if Sales drops >10%"**, ask **"Why did sales drop? forecast"**, → Get:

- 📊 Interactive Plotly charts (line, bar, pie, scatter, heatmap, histogram)
- 📋 Result tables + profiling (nulls, dtypes, duplicates, describe)
- 💡 AI-generated insights in plain English
- 🔒 100% private — data never leaves your server (heuristic or Ollama local mode)
- 📄 Export chart JSON, result CSV, code `.py`, chat history

**No SQL, No Pandas needed.** Try `SELECT * FROM df WHERE Sales > 1000` too — full SQL via DuckDB.

---

## 🔌 Multi-Provider LLM (New in L1)

Works **without any key** (heuristic fallback for 15+ queries). Add any key to `.env` for smarter LLM — first available wins when `LLM_PROVIDER=auto`:

| Provider | Env | Model Default | Get Key |
|----------|-----|---------------|---------|
| **OpenAI** | `OPENAI_API_KEY=sk-...` | `gpt-4o-mini` | [platform.openai.com](https://platform.openai.com) |
| **Groq** (fast, free) | `GROQ_API_KEY=gsk_...` | `llama-3.1-8b-instant` | [console.groq.com](https://console.groq.com) |
| **Gemini** | `GOOGLE_API_KEY=AIza...` | `gemini-1.5-flash` | [aistudio.google.com](https://aistudio.google.com) |
| **Claude** | `ANTHROPIC_API_KEY=sk-ant-...` | `claude-3-5-sonnet-20240620` | [console.anthropic.com](https://console.anthropic.com) |
| **Ollama** (local) | `OLLAMA_URL=http://localhost:11434` | `llama3.1:8b` | `ollama serve && ollama pull llama3.1:8b` |

```bash
# .env
LLM_PROVIDER=auto   # or groq, openai, gemini, claude, ollama
GROQ_API_KEY=gsk_...
```

Check active provider: `GET /api/llm/info` or `GET /health` → `llm.provider`.

Fallback is tested: `pytest` runs with **no key** and still passes 17+ tests.

---

## 🏗 Architecture (L3)

```
Frontend (Streamlit 8501) → FastAPI 8000 → Agent
                                         ├── Planner (heuristic + LLM[h via get_llm()])
                                         ├── Coder (templates + LLM → pandas/duckdb code)
                                         ├── Executor (AST-secured, 5s timeout, plotly JSON)
                                         └── Explainer (bullets + LLM)
                            ↓
                     Pandas + DuckDB + Plotly
                            ↓
                     Filesystem (storage/datasets, storage/conversations, storage/dashboards) + profiling
```

`app/core/llm.py` abstracts all 5 providers (OpenAI SDK → httpx fallback for Groq/Gemini/Claude/Ollama). `app/core/security.py` blocks `os, sys, subprocess, time, threading, ...`, `app/core/profiling.py` handles empty/wide files, `app/core/storage.py` does atomic writes + LRU quota. L3 adds `app/services/dashboard_service.py` + `app/api/dashboards.py` for pin/share/refresh, and Streamlit Dashboard Studio grid + `?share=slug` public view.

See [ARCHITECTURE.md](./ARCHITECTURE.md) and [plans/00_ROADMAP.md](./plans/00_ROADMAP.md).

---

## ⚡ Quick Start (1 Command)

### With Docker (Recommended)
```bash
cp .env.example .env   # add any LLM key (optional) — see table above
docker-compose up --build
# Backend: http://localhost:8000  Docs: http://localhost:8000/docs  LLM: /api/llm/info
# Frontend: http://localhost:8501
```

### Without Docker (Local)
```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# In another terminal - Frontend
cd frontend
pip install -r requirements.txt
streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0
```

> **No Key?** `docker-compose up` works out of the box. Try `Show top 5 products by sales` — heuristic handles it.

---

## 📂 Project Structure (L6 — Automation)

```
.
├── backend/
│   ├── app/
│   │   ├── main.py              # + /api/llm/info, /api/llm/providers
│   │   ├── config.py            # PROJECT_ROOT storage, LLM_PROVIDER, all keys
│   │   ├── api/ (datasets, chat, llm, dashboards, connectors, schedules, reports, slack)
│   │   ├── agent/ (planner→analytics+sql, coder→duckdb+forecast/why/outliers/segment/what-if, executor+analytics safe_globals)
│   │   ├── core/ (profiling, storage, security, llm.py, analytics/{why,forecast,outliers,segments}.py, exporter.py, senders.py)
│   │   └── services/ (chat_service, wrangle_service, dashboard_service, connector_service, scheduler_service, scheduler.py)
│   ├── tests/ (test_api, test_executor, test_profiling, test_security, test_llm, test_upload_edge, test_dashboards, test_connectors, test_analytics, test_automation, test_enterprise, test_cloud, etc.) — 138 passed
│   └── requirements.txt  # APScheduler, reportlab, redis, celery, stripe, cryptography, fsspec/s3fs + polars/duckdb
├── frontend/
│   └── streamlit_app.py         # LLM badge, Cloud (billing/brand/LLM), Market, dashboards, Connect, Analytics, Schedules
├── landing/ # Vite static (pricing/docs, 3 pages)
├── sample_data/ (sales.csv, employees.csv)
├── plans/ (00_ROADMAP + 01..08 levels)
├── storage/ (auto-created, gitignored; workspaces/{ws_id}/ when CLOUD=true)
├── docker-compose.yml # OSS (backend+frontend, redis/worker optional prod profile)
├── docker-compose.prod.yml # Enterprise 3-service
├── docker-compose.cloud.yml # Cloud (backend+frontend+redis+worker+ollama+landing)
├── Makefile
├── LICENSE (MIT)
└── .env.example (all 5 LLM + Stripe/Ollama/CLOUD)
```

---

## 🔌 API (L6)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/datasets/upload` | Upload CSV/Excel/JSON (sanitized filename, 413 if >MAX_UPLOAD_MB, 400 if empty/malformed) |
| GET | `/api/datasets?limit=&offset=` | List (paginated) |
| GET | `/api/datasets/{id}` | Get details + profiling (`inferred_roles`) |
| GET | `/api/datasets/{id}/preview?rows=` | Preview rows |
| GET | `/api/datasets/{id}/download` | Download original CSV |
| DELETE | `/api/datasets/{id}` | Delete + versions |
| POST | `/api/chat` | Chat with data (supports `SELECT ...` SQL) |
| GET | `/api/chat/conversations?dataset_id=&limit=&offset=` | List (paginated, LRU 50 per dataset) |
| GET | `/api/chat/conversations/{id}` | Get conversation |
| DELETE | `/api/chat/conversations/{id}` | Delete conversation (for Clear Chat) |
| GET | `/api/llm/info` | Active provider + available |
| GET | `/api/llm/providers` | Supported list + how-to |
| POST | `/api/dashboards` | Create dashboard `{dataset_id, name, description}` |
| GET | `/api/dashboards?dataset_id=&limit=&offset=` | List dashboards |
| GET | `/api/dashboards/{id}` | Get dashboard + widgets |
| POST | `/api/dashboards/{id}/widgets` | Pin widget `{query, code, result, chart, title}` |
| DELETE | `/api/dashboards/{id}/widgets/{wid}` | Remove widget |
| POST | `/api/dashboards/{id}/widgets/{wid}/refresh` | Re-run code on current data |
| POST | `/api/dashboards/{id}/share` | Create share slug `{slug, url}` |
| POST | `/api/dashboards/{id}/unshare` | Revoke share |
| GET | `/api/dashboards/share/{slug}` | Public (no auth) |
| POST | `/api/dashboards/{id}/duplicate` | Duplicate dashboard |
| GET | `/api/dashboards/{id}/export?format=json|csv|pdf` | Export JSON/ZIP/PDF (reportlab) |
| POST | `/api/dashboards/{id}/comments {text,parent_id?}` | Add comment (max 100/dash) |
| GET | `/api/dashboards/{id}/comments` | List comments |
| DELETE | `/api/dashboards/{id}/comments/{cid}` | Delete comment |
| POST | `/api/connectors` | Create live connector `{kind: postgres|mysql|sqlite|bigquery|sheets, dsn|sheet_url, table, name}` → virtual dataset |
| GET | `/api/connectors` | List connectors |
| GET | `/api/connectors/{id}` | Get connector |
| DELETE | `/api/connectors/{id}` | Delete connector + virtual dataset |
| POST | `/api/connectors/{id}/query {sql,limit}` | Read-only SQL (blocks DDL/DML), returns result+chart |
| POST | `/api/connectors/{id}/test` | Test connection (`SELECT 1`) |
| POST | `/api/datasets/join {ids:[],on,how:left|inner|right|outer}` | DuckDB federation join → new dataset with lineage |
| POST | `/api/schedules {dashboard_id|query,dataset_id,cron,channel:email|slack|both,to,threshold?}` | Create cron schedule (APScheduler) |
| GET | `/api/schedules` | List schedules |
| GET | `/api/schedules/{id}` | Get schedule |
| DELETE | `/api/schedules/{id}` | Delete (+ remove APScheduler job) |
| POST | `/api/schedules/{id}/run` | Manual run (sends email/slack PDF) |
| GET | `/api/schedules/{id}/runs` | Last 5 runs |
| GET | `/api/schedules/{id}/export` | PDF of linked dashboard |
| POST | `/api/reports {dashboard_id,blocks,name}` | Create report (markdown+widget blocks) |
| GET | `/api/reports` | List reports |
| GET | `/api/reports/{id}` | Get report |
| GET | `/api/reports/{id}/export?format=pdf|json|csv` | Export report |
| POST | `/api/auth/register {email,pass,role}` | Register |
| POST | `/api/auth/login {email,pass}` | Login → `JWT` |
| GET | `/api/auth/me` | Current user |
| POST | `/api/auth/api-key {name,scopes}` | Create API key (editor/admin) |
| GET | `/api/auth/api-key` | List keys |
| DELETE | `/api/auth/api-key/{id}` | Delete key |
| GET | `/api/audit?limit=&dataset_id=` | Audit log (admin) |
| GET | `/api/jobs/{id}` | Poll queued chat job |
| POST | `/api/slack/events` | Slack events (verify X-Slack-Signature, url_verification, app_mention) |
| POST | `/api/slack/slash` | Slash `/insight` |
| GET | `/health` | `{status, version, llm}` |
| GET | `/` | `{name, version, llm, storage}` |

Docs: `http://localhost:8000/docs` — try `POST /api/chat` with `{"dataset_id":"...","query":"Why did sales drop in March?"}`. Schedules: `POST /api/schedules` with `0 9 * * 1` + Run Now. PDFs via `reportlab` (no kaleido needed). Connect: `/tmp/demo_connect.sqlite`; Analytics: `statsforecast` else naive.

---

## 🧪 Testing (L8 — 138 tests)

```bash
cd backend
pip install -r requirements.txt
pytest -q              # 138 tests (no key needed)
pytest tests/test_automation.py -v   # schedules/reports/comments/slack/exporter/senders
pytest tests/test_analytics.py -v   # why/outliers/segment/forecast/what-if/correlation
pytest tests/test_connectors.py -v   # sqlite/sheets/bq 501/join/NL→SQL/read-only guard
pytest tests/test_dashboards.py -v   # dashboard pin/share/refresh/export
pytest tests/test_upload_edge.py -v   # malformed, empty, large
pytest tests/test_llm.py -v           # multi-provider detection
pytest tests/test_enterprise.py -v    # auth/rbac/audit/cache/polars/queue/jobs
pytest tests/test_cloud.py -v         # workspaces/billing/brand/llm/marketplace/admin + no-cloud regression
make test              # alias
make cov               # coverage 80%+
make format && make lint
```

CI: `.github/workflows/ci.yml` runs `pytest -q` + `py_compile` on push.

---

## 🏢 Enterprise (L7)

**OSS stays MIT & frictionless** (`AUTH_REQUIRED=false` default → anon editor). Flip for enterprise:

| Flag | Effect |
|------|--------|
| `AUTH_REQUIRED=true` | `POST/DELETE` require `Bearer JWT` or `X-API-Key` |
| `REDIS_URL=redis://redis:6379/0` | Cache (60s) + Queue (202 for forecast/>1M rows) |
| `USE_POLARS=true` | Polars engine for >1M rows (fallback to pandas) |
| `STORAGE_BACKEND=s3` | S3/MinIO via `fsspec` |

- Auth: `POST /api/auth/register`, `/login → JWT`, `GET /me`, `POST /api-key` (editor/admin)
- RBAC: `admin` all, `editor` create/edit, `viewer` read-only — enforced via `get_current_user`
- Audit: `storage/audit/YYYY-MM-DD.jsonl` + `GET /api/audit` (admin)
- Queue: `POST /api/chat` (forecast) → `202 {job_id}` → `GET /api/jobs/{id}`; fallback sync if no Redis/Celery
- Frontend: Sidebar **Login**, hides Delete for viewers, **Audit** tab, queue spinner
- Prod: `docker-compose --profile prod up` or `docker-compose -f docker-compose.prod.yml up` (backend+frontend+redis+worker)
- See [docs/enterprise.md](./docs/enterprise.md) + [plans/07_LEVEL_07_ENTERPRISE.md](./plans/07_LEVEL_07_ENTERPRISE.md)

---

## ☁️ Cloud (L8) — insightagent.com

**Open-core:** OSS `docker-compose up` → `default` workspace, no billing. Cloud `CLOUD=true` → multi-tenant at `app.insightagent.com`.

| Flag | Effect |
|------|--------|
| `CLOUD=true` | `storage/workspaces/{ws_id}/` isolation, JWT `ws_id`, quotas |
| `STRIPE_SECRET_KEY=sk_test_mock` | Mock checkout (no real charge) or real `sk_test_...` + `stripe listen` |
| `OLLAMA_URL=http://ollama:11434` | Per-workspace LLM (`ollama` local, BYOK `openai_key` encrypted) |

- Workspaces: `POST /api/cloud/auth/register {email,pass,workspace_name}` → `ws_id` + `storage/workspaces/{ws_id}/` (`datasets/dashboards/schedules/billing.json`)
- Billing: `GET /api/cloud/billing` (`plan, usage, quotas`), `POST /api/cloud/billing/checkout {plan:pro|team|enterprise}` → Stripe/mock URL, `POST /api/cloud/billing/webhook` verifies `Stripe-Signature` → upgrades `billing.json`; quotas `free: 3 datasets/50 queries/mo` → `402` else `pro: 100/10k` etc
- White-label: `POST /api/cloud/workspaces/{id}/brand {app_name,logo_url,primary_color}` (enterprise 402 else 200) → frontend injects CSS
- LLM: `POST /api/cloud/llm {provider,model,ollama_url,openai_key}` per workspace (Fernet encrypted if `ENCRYPTION_KEY`)
- Marketplace: `GET /api/marketplace` (10 templates) + `POST /api/marketplace/{id}/install {dataset_id}` clones dashboard
- Admin: `GET /api/cloud/admin/stats` (admin) → `{total_workspaces,mrr,active_subscriptions,total_datasets}`
- Frontend ☁️ Cloud tab: **Billing** (plan/usage + Upgrade), **Brand** form, **LLM** selector + BYOK, 🛒 **Market** install; landing at `http://localhost:3000`
- Cloud: `docker-compose -f docker-compose.cloud.yml up` (backend+frontend+redis+worker+ollama+landing); LLM `ollama pull llama3.1:8b` optional
- See [docs/CLOUD.md](./docs/CLOUD.md) + [CLOUD.md](./CLOUD.md) + [plans/08_LEVEL_08_CLOUD.md](./plans/08_LEVEL_08_CLOUD.md)

---

## 🔒 Security (L1 Hardened)

- AST `validate_code` blocks `os, sys, subprocess, time, threading, socket, shutil, pathlib, importlib, pickle, http, ...` + `eval, exec, __import__, open, globals, ...` + `__class__, __mro__, ...` (see `app/core/security.py`)
- Only `pandas, numpy, plotly, duckdb, datetime, json, re, math` implicitly allowed
- Execution in restricted `__builtins__` (no `__import__`) + 5s timeout + thread fallback
- SQL: `validate_sql` blocks `INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE` (coder + storage)
- No network/file access from generated code

---

## 💰 Monetization (Open Core)

- **Self-Hosted:** MIT, free forever (all L1-L6)
- **Cloud Premium:** Hosted at insightagent.com — $19/mo (unlimited, DB connectors, schedules)
- **Enterprise:** On-premise + SSO + Local LLM (Ollama)

---

## 🛣 Roadmap

- [x] **L1 Foundation** — Ingestion hardening, profiling, multi-provider LLM, chat, executor, storage, frontend, CI
- [x] **L2 Wrangling** — Cleaning agent, versioning, preview/apply/undo (isolated `df_clean`, `diff`, writable check)
- [x] **L3 Dashboard** — Pin (instant), grid (2-col), share link (`?share=slug` + `/api/dashboards/share/{slug}`), filters, export (JSON/CSV ZIP), refresh + staleness
- [x] **L4 Connectors** — Postgres/MySQL/SQLite/BigQuery/Sheets, `POST /api/connectors/{id}/query`, DuckDB federation `POST /api/datasets/join`, NL→SQL, read-only guard
- [x] **L5 Analytics** — Why (cohort diff), outliers IQR/Z, segments treemap/bar, forecast (statsforecast/naive), what-if, correlation
- [x] **L6 Automation** — Schedules (APScheduler cron), PDF exporter (reportlab), Email/Slack senders, Slack bot (/insight + verify), Comments (threaded), Reports (markdown+widget → PDF/CSV/JSON) (you are here)
- [ ] L6 Automation — Schedules, Slack, reports
- [ ] L7 Enterprise — Auth, RBAC, cache, queue
- [ ] L8 Cloud — Billing, multi-tenant, white-label

See `plans/` for full 8-level design.

---

## 🤝 Contributing

PRs welcome! Run `make format && make lint && make test` before submitting.

## License

MIT — see [LICENSE](./LICENSE)

## Changelog (L1)

- Multi-provider LLM (`app/core/llm.py`) — OpenAI, Groq, Gemini, Claude, Ollama via `LLM_PROVIDER=auto`
- Ingestion hardened (filename sanitize, 413, empty check, Excel/JSON robust, download endpoint)
- Profiling robust (empty, wide, datetime regex, inferred_roles, 20-col limit)
- Coder: SQL passthrough (`SELECT`), filter `where` improved, no `import` in templates
- Security: extended blocklist + `__import__` block, safe_globals without `__import__`
- Storage: atomic writes, LRU quota, pagination, delete conversation, versions prep
- Frontend: LLM badge, copy/download buttons, error toasts, dataset download, chat export
- Docs: README + ARCHITECTURE + .env.example + LICENSE + CI
