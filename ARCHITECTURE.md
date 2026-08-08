# Architecture — InsightAgent

## Overview

InsightAgent is a **tool-calling AI agent** that turns natural language into **Pandas/Python code**, executes it safely, and returns charts + insights.

## Components

### 1. Frontend (Streamlit)
- File uploader (CSV/Excel/JSON)
- Dataset selector + profiling view
- Chat UI (user query → assistant chart + table + insight)
- Plotly rendering via `st.plotly_chart`
- No state in frontend, all state in backend

### 2. Backend (FastAPI)

#### a. Storage Layer (`core/storage.py`)
- Filesystem storage: `storage/datasets/{id}/original.csv`
- Metadata: JSON files `storage/datasets/{id}/meta.json` (no DB needed for MVP, easily swapped to Postgres)
- Also stores `storage/conversations/{id}.json`

#### b. Profiling (`core/profiling.py`)
- Uses Pandas + DuckDB
- Computes: shape, columns, dtypes, nulls, duplicates, numeric describe, categorical top values, datetime detection, sample rows
- Returns JSON for frontend + for LLM context

#### c. Agent Pipeline (`agent/`)

**Planner (`planner.py`)**
- Classifies intent: `visualization | aggregation | filter | profiling | insight | cleaning`
- Uses LLM if available else heuristics (keyword matching)
- Also extracts: chart hint, columns mentioned, aggregation type

**Coder (`coder.py`)**
- If `OPENAI_API_KEY` set: calls GPT-4o-mini with system prompt → generates code JSON `{code, chart_type}`
- Else: **Rule-based fallback** with 15+ templates:
  - `top N by X`, `sales by category`, `monthly trend`, `correlation`, `distribution`, `average`, `filter where`, etc.
- Templates produce safe Pandas + Plotly code

**Executor (`executor.py`)**
- **Security:** `security.py` parses AST, allows only whitelisted builtins/modules
- Executes in limited globals: `df, pd, np, px, go, duckdb`
- Must produce `result` (DataFrame/Series/dict) and `fig` (Plotly Figure) optionally
- Timeout 5s via `signal` / fallback to thread
- Captures stdout, errors, and converts result to JSON + fig to JSON

**Explainer (`explainer.py`)**
- If LLM: sends result summary to LLM for 2-3 bullet insights
- Else: template insights based on result stats (e.g., "Highest value is X in row Y")

### 3. Data Engine
- **Pandas + Polars** for transforms
- **DuckDB** for SQL on CSV: `SELECT * FROM df WHERE ...` without loading DB
- **Plotly** for all charts, serialized via `fig.to_json()` / `fig.to_dict()`

### 4. Security (`core/security.py`)

Allowed:
- `pandas, numpy, plotly, duckdb, datetime, json, re, math`
Blocked (AST check):
- `import os, sys, subprocess, socket, shutil, pathlib, eval, exec, __import__, open, compile`
- Attribute access: `__class__, __subclasses__, __dict__`
- Calls: `eval, exec, open`

### 5. API Flow

```
POST /api/datasets/upload
  -> save file -> profile -> return DatasetResponse

POST /api/chat {dataset_id, query, conversation_id}
  -> load df from storage
  -> planner.plan(query, profile)
  -> coder.generate(query, profile, intent)
  -> executor.execute(code, df)
  -> explainer.explain(query, result_json, profile)
  -> save to conversation -> return ChatResponse{generated_code, chart_json, table_json, insight}
```

## Scaling

- **MVP:** File storage + single process, sufficient for 100s of users
- **Scale:** Swap `storage.py` to Postgres + S3, add Celery queue for long queries, add Redis cache
- **Multi-tenancy:** Add `user_id` to all storage paths

## Why No Vector DB?

Not needed for MVP — data is tabular, LLM sees profile (schema) not rows. For huge datasets, we sample / profile, not embed.

## Deployment

- **Docker:** backend + frontend as two services, shared volume `storage`
- **Prod:** Fly.io / Railway / Coolify with `docker-compose.yml`
- **Env:** `OPENAI_API_KEY` optional, graceful fallback
