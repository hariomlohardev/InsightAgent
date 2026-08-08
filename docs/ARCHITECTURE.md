# Architecture — InsightAgent (Level 01 Foundation + Multi-Provider LLM)

## Overview

InsightAgent is a **tool-calling AI agent** that turns natural language into **Pandas/Python code**, executes it safely, and returns charts + insights. **L1** adds multi-provider LLM and hardening; later levels add cleaning, dashboards, connectors.

## Components

### 1. Frontend (Streamlit 8501)

- File uploader (CSV/Excel/JSON, sanitized name, 120 char limit, 100MB)
- Dataset selector + profiling tabs (Preview, Profiling, Quick Stats, Chat)
- Chat UI (user → assistant `insight` + `code` + `table` + `chart` + download buttons)
- LLM badge in header (`OPENAI|GROQ|GEMINI|CLAUDE|OLLAMA|heuristic`) from `GET /api/llm/info`
- Copy code (download `.py`), download CSV/JSON, chart JSON, chat export, error toasts
- No state in frontend; all state in backend via `storage/`

### 2. Backend (FastAPI 8000)

#### a. Config (`app/config.py`)

- `PROJECT_ROOT = Path(__file__).parent.parent.parent` → `storage_path = PROJECT_ROOT/storage` (not cwd)
- `Settings` with `extra="ignore"` (allows `BACKEND_URL` etc)
- **LLM:** `LLM_PROVIDER=auto|openai|groq|gemini|claude|ollama`, `LLM_MODEL` override, per-provider keys:
  - `OPENAI_API_KEY`/`OPENAI_MODEL`, `GROQ_API_KEY`/`GROQ_MODEL`, `GOOGLE_API_KEY`/`GEMINI_MODEL`, `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL`, `OLLAMA_URL`/`OLLAMA_MODEL`

#### b. Storage Layer (`core/storage.py`)

- Filesystem: `storage/datasets/{id}/data.csv` + `original.*` + `meta.json` + `versions/0.csv` + `versions/versions.json`
- `storage/conversations/{id}.json` (atomic `tmp.json→rename`, `_default` for numpy, LRU `MAX_CONVERSATIONS_PER_DATASET=50`)
- `storage/datasets` list skips unreadable (permission handled), sorted by `created_at` desc, paginated via `limit/offset`
- Also `storage/connectors/` in L4, `storage/dashboards/` in L3, `storage/schedules/` in L6

#### c. Profiling (`core/profiling.py`)

- Handles empty df, wide files (>20 cols limit describe), dirty files
- For each col: `dtype`, `nulls`, `unique`, `sample_values`, `stats` (if numeric), `top_values` (if categorical), `inferred_type` (datetime via regex + `pd.to_datetime(errors="coerce")`, not `raise`)
- Returns `inferred_roles: {col: measure|dimension|datetime}` + `numeric_columns`, `categorical_columns`
- `get_profile_summary_text` includes roles for LLM

#### d. LLM Abstraction (`core/llm.py`) — New in L1

- `LLMProvider` base + 5 implementations:
  - `OpenAIProvider` (uses `AsyncOpenAI` or `httpx` fallback) + `GroqProvider` (base_url `https://api.groq.com/openai/v1`)
  - `GeminiProvider` (SDK `google.generativeai` or `httpx` to `generativelanguage.googleapis.com`)
  - `ClaudeProvider` (SDK `anthropic` or `httpx` to `api.anthropic.com`)
  - `OllamaProvider` (`httpx` to `OLLAMA_URL/api/chat`, `format=json` when `json_mode`)
- Factory `get_llm()` picks `LLM_PROVIDER` or `auto` → first available key in order `openai→groq→gemini→claude→ollama`
- `extract_json` handles markdown fences
- `get_llm_info()` for `/api/llm/info`

#### e. Agent Pipeline (`agent/`)

**Planner (`planner.py`)**
- Heuristic keywords (`visual, agg, filter, profile, insight, cleaning`) + `ChartMap`
- Now uses `get_llm()` → `llm.chat(SYSTEM_PLANNER_PROMPT, f"Query: {q}\nColumns: {cols}", json_mode=True)` → `extract_json` → fallback to heuristic

**Coder (`coder.py`)**
- Priorities: `0. SQL passthrough` (`SELECT`/`WITH` → `duckdb.query`) → `1. Top N` (fixed cat/num swap) → `2. Trend` (no `import`, `freq='ME'`) → `3. Correlation` → ... → `8. Filter where` (regex `where` + `greater than`→`>`, `duckdb` fallback) → `13. Default`
- All templates use `pd, np, px, go, duckdb` already in `safe_globals`; **no `import` in generated code** (tested)
- `generate_code` uses `get_llm()` → `SYSTEM_CODER_PROMPT` + `profile_summary` + `intent` → `extract_json` → fallback to `fallback_coder`

**Executor (`executor.py`)**
- `validate_code` (from `security.py`) → `get_safe_globals(df)` → `execute_with_timeout` (signal + thread) → `result`+`fig` → `dataframe_to_json` (trunc 100) + `fig_to_json` (via `fig.to_json()` → `json.loads`, then `_convert` ndarray→list)
- Captures `stdout`, `error`

**Explainer (`explainer.py`)**
- `fallback_explain` (template) vs `get_llm()` → `SYSTEM_EXPLAINER_PROMPT` → `llm.chat`

#### f. Security (`core/security.py`) — Hardened L1.4

- `BLOCKED_MODULES`: `os, sys, subprocess, socket, shutil, pathlib, importlib, time, threading, multiprocessing, ctypes, pickle, http, urllib, ...` (20+)
- `BLOCKED_NAMES`: `eval, exec, compile, __import__, open, input, globals, ...`
- `BLOCKED_ATTRS`: `__class__, __mro__, __globals__, __code__, ...`
- `validate_code` walks AST, blocks `Import`, `ImportFrom`, `Call` (`Name` or `Attribute` on blocked module), `Attribute`
- `get_safe_globals` provides **limited `__builtins__`** (no `__import__`, no `open`)

#### g. Services

- `chat_service.process_query_v2`: `load_dataset_df` → `profile` → `planner` → `coder` → `executor` → `explainer` → `save_conversation_message` (user + assistant)
- `connector_service`, `dashboard_service` in L3-4

### 3. Data Engine

- **Pandas** (default) + **Polars** (optional for >1M rows, L7) + **DuckDB** (`1.0.0`, `READ_ONLY` for SQL)
- **Plotly** (`5.22.0`) for charts, serialized via `fig.to_json()` → `json.loads`

### 4. API Flow (L1)

```
POST /api/datasets/upload (sanitize, 400 if empty/unsupported, 413 if >MAX_UPLOAD_MB)
  -> save_dataset (try utf-8/ latin1, sep detection, Excel via openpyxl/xlrd, JSON multi-orient, atomic meta)
  -> meta.json (rows, cols, column_names, current_version=0)

GET /api/datasets?limit=&offset=  -> list_datasets (skip unreadable, sorted)

POST /api/chat {dataset_id, query, conversation_id}
  -> load df
  -> profile (with inferred_roles)
  -> planner (LLM or heuristic)
  -> coder (SQL → duckdb, else templates)
  -> executor (AST check, 5s)
  -> explainer (LLM or fallback)
  -> save_conversation_message (atomic, LRU 50)
  -> ChatResponse

GET /api/llm/info  -> {provider, model, configured, available_providers}
GET /api/llm/providers -> supported + how-to
```

### 5. Validation & Deployment

- **Tests:** `backend/tests` — 62 tests (heuristic, LLM detection, upload edge, profiling robust, security hardened, executor fig, storage quota, api, etc.) all via `pytest -q` **without any API key**
- **CI:** `.github/workflows/ci.yml` (setup-python, pip, black, ruff, py_compile, pytest)
- **Docker:** `docker-compose.yml` (backend 8000 + frontend 8501, `STORAGE_PATH=/app/storage`, all LLM env passthrough, healthcheck; optional `ollama` profile)
- **Makefile:** `make test`, `make cov`, `make format`, `make lint`, `make check`
- **Frontend:** Streamlit, LLM badge, copy/download, error toasts, pagination

### 6. Next Levels

- L2: `core/wrangle.py` + `versions/` Apply/Undo
- L3: `core/storage` dashboards + `api/dashboards`
- L4: `core/connectors` + DuckDB federation
- See `plans/00_ROADMAP.md` for full 8.
