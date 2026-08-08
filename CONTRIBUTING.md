# Contributing to InsightAgent

> 5 minutes from clone to PR. All checks run with `make`.

## Quick Start (3 steps, 30s)

```bash
git clone https://github.com/your-org/insightagent && cd insightagent
make install          # backend + frontend deps (pip install -r backend/requirements.txt + frontend)
make test             # 151 tests, ~40s (filesystem fallback, no DB needed)
make lint             # black + ruff + py_compile
```

Then `make docker-up` or `make backend` + `make frontend` in two terminals:

```bash
make backend   # http://localhost:8000/docs  (FastAPI)
make frontend  # http://localhost:8501       (Streamlit)
# Upload sample_data/sales.csv -> chat "top 5 products by sales"
```

## Adding a Connector (Plugin API)

Connectors are `BaseConnector` entry_points (`insightagent.connectors`).

```bash
# 1. Create plugin package
mkdir -p my_plugin && cat > my_plugin/connector.py <<'PY'
from app.plugins import BaseConnector
import pandas as pd
class MyConnector(BaseConnector):
    kind = "my_db"
    def fetch(self, params: dict, limit: int = 1000) -> pd.DataFrame:
        # params from frontend form (host, query, etc.)
        return pd.DataFrame({"a":[1,2]})
    def validate(self, params: dict) -> str | None:
        if not params.get("host"): return "host required"
PY
# 2. Register via pyproject.toml
# [project.entry-points."insightagent.connectors"]
# my_db = "my_plugin.connector:MyConnector"
pip install -e .
# 3. Frontend auto-discovers it via importlib.metadata.entry_points
```

See `examples/my_connector.py` and `app/plugins/__init__.py`.

## Adding an Analyzer

```python
from app.plugins import BaseAnalyzer
class MyAnalyzer(BaseAnalyzer):
    name = "my_insight"
    def analyze(self, df, query: str) -> dict:
        return {"insight": f"rows={len(df)}"}
# entry point: [project.entry-points."insightagent.analyzers"]
```

## Project Layout

```
backend/app/{api,core,agent,services,plugins}  FastAPI + storage (FS/DB/S3)
frontend/streamlit_app.py                      Streamlit 1.39
sdk/insightagent/                              pip install insightagent
docs/                                          Docusaurus site
sample_data/                                   sales.csv etc.
```

## Making a PR

1. Branch `feat/my-thing`, run `make lint && make test` (0 errors)
2. Follow `SECURITY.md` for sensitive data, `CODE_OF_CONDUCT.md` for behavior
3. Describe `why` + `how` + `bench` if perf; link issue template
4. CI runs `black --check` + `ruff` + `pytest -q` + `py_compile frontend`

## Troubleshooting

* `DATABASE_URL` empty → filesystem fallback (no Postgres needed). For DB: `docker compose --profile db up -d` + `DATABASE_URL=postgresql+asyncpg://...`
* `STORAGE_BACKEND=s3` → needs `S3_BUCKET` + `AWS_*` (tests use `moto` mock, no AWS)
* `OTEL_EXPORTER_OTLP_ENDPOINT` empty → no-op; `SENTRY_DSN` empty → no-op
* `USE_POLARS=true` needs `polars`; fallback to `pandas chunksize` if missing

## Release

`git tag v1.0 && git push --tags` → CI builds, `BENCHMARKS.md` updated via `scripts/bench_*.py`.
