# InsightAgent — AI Data Analyst

**Chat with your CSV/Excel/SQL in plain English. Get charts & insights in seconds.**

Open source alternative to Tableau + ChatGPT Code Interpreter | Python | **OpenAI / Groq / Gemini / Claude / Ollama**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green) ![Streamlit](https://img.shields.io/badge/Streamlit-1.39-red) ![License](https://img.shields.io/badge/License-MIT-yellow) ![Tests](https://img.shields.io/badge/tests-156%20passed-brightgreen) ![Bench](https://img.shields.io/badge/10M-1.38s-blue)

> `make install && docker-compose up` → http://localhost:8501 — no key required (heuristic fallback)

![Demo](docs/static/img/demo.gif)

---

## What it does

Upload CSV/Excel/JSON or connect **Postgres/MySQL/SQLite/BigQuery/Sheets** → ask *“Why did sales drop? forecast next 3 months, segment by Region”* → get Plotly charts, tables, and plain-English insights. 100% private — data stays on your server (local `heuristic` or `ollama`).

* No SQL/Pandas needed (but `SELECT` via DuckDB works)
* Interactive charts + profiling (`nulls`, `dtypes`, `duplicates`)
* Export chart JSON / CSV / `.py` / chat history

---

## Quick start

```bash
cp .env.example .env  # add LLM key if you have one (optional)
docker-compose up --build
# Backend  http://localhost:8000  Docs http://localhost:8000/docs
# Frontend http://localhost:8501
```

Without Docker:

```bash
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000
cd frontend && pip install -r requirements.txt && streamlit run streamlit_app.py --server.port 8501
```

---

## LLM providers (all optional)

Heuristic handles 15+ queries with **no key**. Add any key — `LLM_PROVIDER=auto` picks first available.

| Provider | Env | Default model |
|----------|-----|---------------|
| OpenAI | `OPENAI_API_KEY=sk-...` | `gpt-4o-mini` |
| Groq | `GROQ_API_KEY=gsk_...` | `llama-3.1-8b-instant` |
| Gemini | `GOOGLE_API_KEY=AIza...` | `gemini-1.5-flash` |
| Claude | `ANTHROPIC_API_KEY=sk-ant-...` | `claude-3-5-sonnet` |
| Ollama | `OLLAMA_URL=http://localhost:11434` | `llama3.1:8b` |

Check: `GET /api/llm/info` or `GET /health`.

---

## Features

* **Chat** — Planner → Coder → Executor (AST-secured, 5s) → Explainer; 14 templates, no `import` in code, SQL passthrough
* **Wrangling** — preview/apply/undo cleaning, versioning
* **Dashboards** — pin grid, `?share=slug` public, export JSON/CSV/PDF
* **Connectors** — live `query` + DuckDB `join` on 2–3 datasets
* **Analytics** — `why`/`outliers`/`segment`/`forecast`/`what-if`/`correlation`
* **Automation** — cron schedules → Email/Slack PDF, Slack `/insight`, comments, reports
* **Enterprise** — `AUTH_REQUIRED`, `REDIS_URL` cache/queue, `USE_POLARS`, `S3` (all fallback to FS)
* **Cloud** — `CLOUD=true` workspaces, billing (Stripe mock), white-label, per-workspace LLM

See [ARCHITECTURE.md](./ARCHITECTURE.md) and [plans/00_ROADMAP.md](./plans/00_ROADMAP.md).

---

## Project structure

```
backend/app/{main,config,api,agent/{planner,coder,executor},core/{profiling,storage,security,llm},services}
frontend/streamlit_app.py
scripts/bench_*.py  sample_data/  plans/  storage/ (gitignored)
```

---

## API

Full spec at `http://localhost:8000/docs`. Key endpoints:

`POST /api/datasets/upload` · `GET /api/datasets/{id}` (`X-Cache`) · `POST /api/chat` (`X-Cache:HIT` <5ms) · `POST /api/dashboards/{id}/widgets` · `POST /api/connectors/{id}/query` · `POST /api/datasets/join` · `POST /api/schedules` · `GET /health`

---

## Benchmarks (BLAZFAST)

* 1M rows `polars 1.38s` (was 1.79s) — vectorized profile, streaming read 39ms vs 205ms
* Chat repeat `3.5ms HIT` (was 4.6s) — `chat:{id}:{qhash}:{version}` cache
* Frontend `describe` -33% payload, paginated

Details: [BENCHMARKS.md](./BENCHMARKS.md) + [BENCHMARKS.json](./BENCHMARKS.json) (machine-readable, per-col)

---

## Testing

```bash
cd backend && pip install -r requirements.txt && pytest -q          # 156 tests, no key
make lint && make test   # black + ruff + mypy + py_compile + pytest
```

CI: `.github/workflows/ci.yml` runs `lint` + `backend (3.10/11/12 + PG/Redis)` + `bench 100k <1s` + `frontend AppTest` + `docker config` → required `gate`.

---

## Docs

> **Placeholder — full docs coming.** Start with:

* [ARCHITECTURE.md](./ARCHITECTURE.md) — components + data flow
* [CONTRIBUTING.md](./CONTRIBUTING.md) — `make install && docker-compose up` in 30s
* [BENCHMARKS.md](./BENCHMARKS.md) — how to reproduce
* [CLOUD.md](./CLOUD.md) / [docs/](./docs/) — cloud & enterprise

A `docs/` site (Docusaurus) will live at `/docs` — PRs welcome. For now, see `plans/` and `plan/blazfast/` for the blazing-fast roadmap.

---

## Contributing

PRs welcome! `make format && make lint && make test` before pushing. See [CONTRIBUTING.md](./CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).

## License

MIT — see [LICENSE](./LICENSE)
