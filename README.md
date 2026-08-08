# InsightAgent — AI Data Analyst Agent

**Chat with your CSV/Excel/SQL in plain English. Get charts, insights & reports in seconds.**

> Open Source Alternative to Tableau + ChatGPT Code Interpreter + Power BI | Built with Python

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green) ![Streamlit](https://img.shields.io/badge/Streamlit-1.35-red) ![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 🚀 What It Does

Upload any CSV/Excel → Ask **"Show monthly sales trend, why did sales drop in March?"** → Get:

- 📊 Interactive Plotly charts (line, bar, pie, scatter, heatmap, histogram)
- 📋 Result tables + profiling
- 💡 AI-generated insights in plain English
- 📄 Export to PNG / PDF / Excel

**No SQL, No Pandas knowledge needed.** Data never leaves your server if you use Local LLM mode.

---

## 🏗 Architecture

```
Frontend (Streamlit) → FastAPI → LangGraph Agent
                                    ├── Planner (intent)
                                    ├── Coder (LLM or rule-based → Pandas code)
                                    ├── Executor (Docker-sandbox, AST-checked)
                                    └── Explainer (chart + insight)
                        ↓
                Pandas/Polars + DuckDB + Plotly
                        ↓
                Postgres/Filesystem + S3/MinIO
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for deep dive.

---

## ⚡ Quick Start (1 Command)

### With Docker (Recommended)
```bash
cp .env.example .env   # add OPENAI_API_KEY if you have it (optional)
docker-compose up --build
# Backend: http://localhost:8000  Docs: http://localhost:8000/docs
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
streamlit run streamlit_app.py --server.port 8501
```

> **No OpenAI Key?** Works anyway! Falls back to rule-based coder covering 15+ common queries (top N, groupby, trend, correlation, etc.)

---

## 📂 Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/ (datasets, chat)
│   │   ├── agent/ (planner, coder, executor, explainer)
│   │   ├── core/ (profiling, storage, security)
│   │   └── services/
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   └── streamlit_app.py
├── sample_data/
│   ├── sales.csv
│   └── employees.csv
├── docker-compose.yml
└── storage/ (auto-created)
```

---

## 🔌 API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/datasets/upload` | Upload CSV/Excel/JSON |
| GET | `/api/datasets` | List datasets |
| GET | `/api/datasets/{id}` | Get details + profiling |
| GET | `/api/datasets/{id}/preview` | Preview rows |
| DELETE | `/api/datasets/{id}` | Delete |
| POST | `/api/chat` | Chat with data |
| GET | `/api/chat/conversations` | List conversations |
| GET | `/health` | Health check |

Docs: http://localhost:8000/docs

---

## 🧪 Testing

```bash
cd backend
pytest -v --tb=short
# or
make test
```

---

## 🔒 Security

- AST-based code validation — blocks `os, sys, subprocess, socket, eval, exec, open`
- Only `pandas, numpy, plotly, duckdb` allowed
- Execution in isolated namespace with timeout (5s)
- No network/file access from generated code

---

## 💰 Monetization (Open Core)

- **Self-Hosted:** MIT, free forever
- **Cloud Premium:** Hosted at insighagent.com — $19/mo (unlimited, DB connectors, scheduled reports)
- **Enterprise:** On-premise + SSO + Local LLM

---

## 🛣 Roadmap

- [x] MVP: Upload + Chat + Charts + Insights
- [ ] Phase 2: SQL connector, Dashboard builder, PDF export
- [ ] Phase 3: Forecast, Slack bot, API

---

## 🤝 Contributing

PRs welcome! Run `make format && make test` before submitting.

## License

MIT
