# Level 5 — Deep Analytics: Stats, Outliers, Cohorts & Forecasting (OSS)

> **From "what happened" to "why" and "what next."**

---

## Goal

Add **statistical deep-dives + forecasting** that a junior analyst would do. After Level 5, you can say *"Why did sales drop in March? Show outliers, correlation, segment by Region, and forecast next 3 months."* and get **a report with 3 explanations + charts + a forecast line**.

## Success Criteria

- [ ] **Why analysis:** `POST /api/chat` with `why|explain|drop|increase` → `insight` does cohort comparison (e.g., March vs Feb: Product A -80%, Region North -40%), not just generic template
- [ ] **Stats:** `correlation`, `distribution`, `outliers` (IQR or Z-score) return stats tables + annotated charts (outliers highlighted in red)
- [ ] **Segments:** `segment by {col}` or `cohort by {col}` → `groupby` with `share` + `growth` columns + `treemap` or `stacked bar`
- [ ] **Forecast:** `forecast {metric} for next {N} months/weeks` → uses `Prophet` or `statsforecast` (ETS/ARIMA) on time-series `Date` col → `result` (history+forecast) + `fig` (line + confidence band) + `metrics` (MAE, RMSE via backtest on last 20% if >20 points)
- [ ] **What-if:** `what if {col} increased 10%` → clones df, applies `*1.1`, re-runs last `groupby` and shows delta table
- [ ] `pytest` 70+ tests (add 10), `py_compile` clean, no regression on L1-L4; forecast works on `sales.csv` (24 rows) as demo even if small
- [ ] Frontend has `📈 Analytics` tab with 1-click buttons: `Explain drop`, `Outliers`, `Forecast`, `Correlation`

## Context & Current Facts

**L4 delivered:**
- Live connectors + JOIN + NL→SQL, dashboard snapshots, cleaning versioning, 60+ tests.

**Pain:** Chat gives a chart but not the **story**. User asks "why drop?" and gets a line chart of sales trend, not the **attribution** (which product, which region). Forecast is manual in Excel; want *"forecast next quarter"* in one sentence.

**Libs already:**
- `pandas`, `numpy`, `plotly`, `duckdb` installed. `Prophet`/`statsforecast` **not** yet — add as optional (`pip install prophet==1.1.5` or `statsforecast`). For L5 OSS, use `statsforecast` (lighter, no Stan) + fallback to naive `last-value` if not installed.

## Constraints & Non-Goals

**Constraints:**
- Stay MIT, stay filesystem, keep Streamlit
- Forecast must work on **small data** (24 rows) for demo, even if less accurate; show warning "Low data, forecast is indicative"
- No GPU, no heavy `prophet` compile on 2GB RAM → prefer `statsforecast` (pure Python + numba)

**Non-Goals (for L5):**
- No causal inference (DoWhy) — defer to post-L8
- No anomaly detection on streaming (L6 scheduling can add)
- No AutoML (H2O) — simple ETS/ARIMA is enough for L5
- No cross-dataset forecast join (single dataset only)

## Key Decisions

| Decision | Recommended | Why |
|----------|-------------|-----|
| **Why engine** | Rule-based `why_analyzer.py` that does **cohort diff**: split data by `time` (pre vs post) or by `category`, compute `delta`, `share`, `contribution` (delta * share), rank top 3 contributors, then LLM (if key) polishes to bullets | Alt: pure LLM "explain" is hallucination; rule-based with numbers is trustworthy, LLM only for prose |
| **Outliers** | `IQR` (`Q1-1.5*IQR`, `Q3+1.5*IQR`) on selected numeric col, plus `Z>3` option; highlight in `px.scatter` with `color=outlier_flag` | Alt: IsolationForest is heavy; IQR is explainable, one-liner pandas |
| **Forecast** | `statsforecast` (`AutoETS`, `AutoARIMA`) with fallback to `naive` (repeat last) and `historical average`; if `prophet` installed, offer as `kind=prophet` | Alt: `Prophet` alone needs `pystan` compile (300MB, slow); `statsforecast` is 10MB, CPU-friendly, MIT |
| **Segments** | `groupby` + `agg(sum, mean, count)` + `pct_change` when time present; chart `px.treemap` for share or `px.bar` stacked | Alt: custom cohort lib overkill; pandas does it |
| **What-if** | Clone `df` → `df_whatif = df.copy(); df_whatif[col] *= 1.1` → re-run stored `code`'s groupby on both and diff | Alt: LLM what-if is vague; re-execution is precise |
| **Frontend** | New `📈 Analytics` tab with buttons + chat shortcut `🔍 Why did sales drop in March?` pre-filled | Alt: new page adds nav; tab keeps flow |

## Recommended Approach

Add **one new service** `app/services/analytics_service.py` + helpers `app/core/analytics/ (why.py, forecast.py, outliers.py, segments.py)` and extend `coder` with `analytics` intent.

Reuse `executor` (forecast code also sandbox-checked, but allow `statsforecast` import in allowlist).

### Data Flow

```
Chat "why..." → planner (insight) → coder (analytics branch) → "why_analyzer.py" logic → executor → result (top contributors table) + fig (waterfall or bar) → explainer → bullets
Chat "forecast..." → coder → "forecast.py" (statsforecast) → result (history+forecast df) + fig (line+band) → explainer
Chat "outliers in Sales" → coder → outliers.py → result + fig (scatter with red)
UI buttons → same POST /api/chat with canned queries
```

## Work Plan (Ordered)

### Unit 5.1 — Why Analyzer (1.5 days)
**Surfaces:** `backend/app/core/analytics/why.py` (new), `app/agent/coder.py`, `app/agent/planner.py`
- [ ] **5.1.1** `why.py`: `analyze_why(df, profile, query)` → detects `drop|increase|change` + `when` (March) + `metric` (Sales) → splits `df` into `pre` (before March) and `post` (March) (or `groupby` if no time), computes per-category deltas, ranks contributors, returns `{top_contributors: [{category, delta, share}], period: "Feb vs Mar"}`
- [ ] **5.1.2** `coder`: add `analytics` branch **before** cleaning/groupby, for `why|explain|drop|increase|reason` → `code = f"result = why_analyzer(df, '{metric}', '{period}')\nfig = px.bar(result, x='category', y='delta')"` (import `why` in `safe_globals`)
- [ ] **5.1.3** Keep deterministic: `why` is rule-based, not LLM
**Validation:** `pytest tests/test_why_analyzer.py` (March drop: Product A -80% is top).

### Unit 5.2 — Outliers & Stats (1 day)
**Surfaces:** `backend/app/core/analytics/outliers.py` (new), `coder.py`
- [ ] **5.2.1** `outliers.py`: `find_outliers(df, col, method="iqr")` → `Q1, Q3, IQR, lower, upper, df_flagged` + `fig`
- [ ] **5.2.2** `coder` branch for `outliers|anomalies|outlier` → code calls `find_outliers`
- [ ] **5.2.3** Extend `profiling.py` `describe` already does stats; add `correlation` already handled in L1, keep
**Validation:** `pytest tests/test_outliers.py` (inject outlier 1M in sales.csv, detect 1).

### Unit 5.3 — Segments / Cohorts (1 day)
**Surfaces:** `backend/app/core/analytics/segments.py` (new), `coder.py`
- [ ] **5.3.1** `segments.py`: `segment(df, by, metric, agg=sum)` → `groupby` + `share`, `pct_change` if time
- [ ] **5.3.2** `coder` branch for `segment by|cohort by|breakdown by`
**Validation:** `pytest tests/test_segments.py`.

### Unit 5.4 — Forecast Engine (2 days)
**Surfaces:** `backend/app/core/analytics/forecast.py` (new), `coder.py`, `app/agent/executor.py` (allow `statsforecast`)
- [ ] **5.4.1** Add `statsforecast` to `backend/requirements.txt` as optional (`statsforecast==1.7.7`), `prophet` as extra (`prophet==1.1.5; extra == "forecast"`)
- [ ] **5.4.2** `forecast.py`: `forecast(df, date_col, metric, periods=3, freq='M')` → resample to `ME`, fit `AutoETS`/`AutoARIMA` via `StatsForecast`, predict `periods`, backtest last 20% for MAE/RMSE, return `history+forecast` df + `fig` (line + `lo/hi` band) + `metrics`
- [ ] **5.4.3** `coder` branch for `forecast|predict|next.*months` → `code = f"result, fig = forecast(df, '{date_col}', '{metric}', {periods})"`
- [ ] **5.4.4** Allow `statsforecast`, `pandas` in `security.py` (add `statsforecast` to `ALLOWED_MODULES`)
- [ ] **5.4.5** Fallback: if `statsforecast` not installed, `forecast.py` does naive `last_value` + warning
**Validation:** `pytest tests/test_forecast.py` (24-row sales.csv, periods=3, check `result.rows == 27` (24+3) and `metrics` present if >20 rows).

### Unit 5.5 — What-If (0.5 day)
**Surfaces:** `backend/app/core/analytics/why.py` (add `what_if`), `coder.py`
- [ ] **5.5.1** `what_if(df, col, pct=10, metric, by)` → clone, `*=(1+pct/100)`, re-agg, diff
- [ ] **5.5.2** `coder` branch for `what if.*increased|decreased.*10%`
**Validation:** `pytest tests/test_whatif.py`.

### Unit 5.6 — API & Chat Wiring (1 day)
**Surfaces:** `backend/app/services/analytics_service.py` (new), `app/agent/coder.py`, `app/services/chat_service.py`
- [ ] **5.6.1** Wire `planner` to detect `forecast|outlier|segment|why|what if` → `intent=analytics`
- [ ] **5.6.2** Ensure `safe_globals` in `executor` includes `why`, `outliers`, `segments`, `forecast` modules (import and inject)
**Validation:** `TestClient` loop: `why drop in March`, `outliers in Sales`, `segment by Region`, `forecast sales next 3 months`, `what if Price increased 10%` all `success=true`.

### Unit 5.7 — Frontend: Analytics Tab (1.5 days)
**Surfaces:** `frontend/streamlit_app.py`
- [ ] **5.7.1** New `📈 Analytics` tab: 5 buttons (`Explain drop`, `Outliers`, `Segment by`, `Forecast`, `What-if`) each pre-fills chat input; also show `Are you seeing drop? [Analyze]` when `insight` contains `drop`
- [ ] **5.7.2** Render forecast chart with confidence band (`go.Scatter` fill), show metrics `MAE/RMSE` in `st.metrics`
- [ ] **5.7.3** For `why`, show `st.dataframe(top_contributors)` + waterfall chart (if available)
**Validation:** Manual: open `sales.csv` → Analytics → Forecast 3 months → see band + metrics; Outliers → see red dots.

### Unit 5.8 — Docs & Release (0.5 day)
- [ ] Tag `v0.5-analytics`, GIF, release notes, update `README` Analytics section

**Total: ~8 days (3 weeks)**

## Validation Plan

| Check | Command | Expected |
|-------|---------|----------|
| All tests | `pytest tests -q` | 70+ passed |
| Why | `pytest tests/test_why_analyzer.py -v` + `TestClient` why drop | top contributor correct |
| Outliers | `pytest tests/test_outliers.py` | 1 outlier detected |
| Forecast | `pytest tests/test_forecast.py` | 24→27 rows, fig present, no crash if small data |
| Segments | `pytest tests/test_segments.py` | groupby share correct |
| What-if | `pytest tests/test_whatif.py` | delta computed |
| Chat | 5 canned analytics queries via `TestClient` | all success |
| Frontend | Manual Analytics tab | 5 buttons work |
| Regression | `python /tmp/e2e_15_queries.py` | still 15/15 |

**Highest-risk:** Forecast on small data (24 rows) is noisy. Mitigate by showing `⚠️ Low data` warning and backtest metrics so user sees accuracy.

## Risks / Rollback

| Risk | Mitigation | Rollback |
|------|------------|----------|
| `statsforecast` adds 50MB + `numba` compile slow on 2GB RAM | Make optional (`pip install -e ".[forecast]"`), fallback to naive if not installed | Remove from `requirements.txt`, keep naive |
| `why` ranking is wrong when no time col | Fallback to category ranking (no time split) | Revert `why.py` to simple groupby diff |
| `executor` allowlist blocks `statsforecast` | Add to `ALLOWED_MODULES`, test | Remove from allowlist, keep fallback |
| Frontend forecast band complicates Plotly | Test `go.Scatter` fill on sample, keep simple line if fails | Revert to `px.line` only |

## Open Questions

- None. `statsforecast` is MIT, CPU-friendly, proven for small data. `IQR` and `why` are simple pandas.

---

**Approval Gate:** Reply `Approve` to build Level 5, or `Change` to edit.
