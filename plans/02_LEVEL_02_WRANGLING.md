# Level 2 — Wrangling Agent: Data Cleaning & Transformation (OSS)

> **"Fix my data" in plain English. No Excel gymnastics.**

---

## Goal

Give users a **natural-language data cleaner** on top of Level 1's foundation. After Level 2, you can say *"remove duplicates, fill missing Price with median, convert Date to datetime, drop rows where Sales=0, rename Customer_Segment to Segment, and show me the before/after"* — and get a **preview, a diff, one-click Apply, and Undo**.

## Success Criteria

- [ ] Chat understands 12+ cleaning intents: `remove duplicates`, `fill nulls (mean/median/mode/forward fill)`, `drop rows/columns`, `rename`, `change type (to datetime/numeric/string)`, `trim whitespace`, `drop duplicates on col`, `remove outliers`, `split column`, `merge columns`, `pivot/melt`, `standardize case`
- [ ] Every cleaning operation returns **preview** (`head(10) before/after` + `diff summary: rows changed, nulls fixed, dtypes changed`) and does **not** mutate the original until user clicks **Apply**
- [ ] Apply creates a **new version** (`datasets/{id}/versions/{v}.csv` + `versions.json`) with **Undo** (revert to previous version); UI shows version history (v0 original, v1, v2...)
- [ ] `profile_dataframe` after cleaning shows updated `null_summary`, `dtypes`, `duplicates` — verified by `tests/test_wrangling_profile.py`
- [ ] All cleaning code is **sandboxed** (same `executor.py` allowlist, no `os`), and is **deterministic** (snapshot tests for each intent)
- [ ] `pytest` 40+ tests (add 10 new), `py_compile` clean, `docker-compose up` still <2 min
- [ ] README adds "Cleaning" GIF + example prompts

## Context & Current Facts

**L1 delivered:**
- Ingestion (CSV/XLSX/JSON), profiling, chat→code→chart, insights, AST security, filesystem storage (`data.csv` + `meta.json` + `conversations/{id}.json`), Streamlit with 3 tabs + chat, 17→30 tests.
- `coder.py` has 15 templates but **no** `cleaning` handling beyond heuristic (`CLEANING_KEYWORDS` detected but no code path). `planner.py` classifies `cleaning` but `coder` falls through to default groupby (wrong).
- `storage.py` has single `data.csv` per dataset, no versioning, no atomic write (now atomic after L1 fix), no quota.

**Pain this solves:**
- Real CSVs are dirty: `sales.csv` has 0 nulls but `employees.csv` has none; real user uploads will have nulls, wrong types (`Date` as string), duplicates, extra spaces. Users currently must clean in Excel before upload — defeats "chat with your data".
- Competitors (ChatGPT, Julius) do cleaning but not self-hosted + versioned + undo.

## Constraints & Non-Goals

**Constraints:**
- Stay MIT, no new paid service
- No DB migration — keep filesystem, add `versions/` subfolder
- No UI framework swap — stay Streamlit, add 1 new tab

**Non-Goals (for L2):**
- No dashboard (L3), no SQL (L4), no forecast (L5), no scheduling (L6)
- No `pivot` UI builder — just natural-language pivot (UI builder in L3)
- No `remove outliers via IQR` beyond simple `mean±3σ` (advanced outlier in L5)

## Key Decisions

| Decision | Recommended | Why (Alt Rejected) |
|----------|-------------|-------------------|
| **Wrangling engine** | Keep `pandas` + `numpy` operations, generated via `coder` templates | Alt: `OpenRefine` integration heavy, `polars` faster but adds wheel; pandas covers 95% of cleaning, well-known |
| **Versioning** | Filesystem `storage/datasets/{id}/versions/{v}.csv` + `versions.json` (id, parent, op, prompt, code, created_at) + `current_version` pointer in `meta.json` | Alt: `git` for data (DVC) overkill, `DB` adds ops; filesystem is simplest for OSS self-host |
| **Preview vs mutate** | `preview` mode: `executor` runs code on **in-memory df copy**, returns `result` + `diff`, but **does not** save until `POST /api/datasets/{id}/apply` | Alt: auto-mutate on chat is dangerous (user loses original); preview+apply is safe, like Git |
| **Undo** | `POST /api/datasets/{id}/revert?version=v` copies `versions/{v}.csv` to `data.csv` + updates `meta.current_version` | Alt: incremental diff log complex; full-file versions are simple, storage cheap (<100MB) |
| **Intent scope** | 12 intents above, each with 1-2 template slots (`fillna` needs `col` + `strategy`) | Alt: free-form LLM code generation is non-deterministic for cleaning; templates are testable, then LLM can refine |
| **UI** | New tab `🧹 Clean` in Streamlit: left = chat box "Describe cleaning", right = before/after preview + diff + Apply/Undo buttons + version history | Alt: separate page adds nav; tab keeps single-page flow |

## Recommended Approach

Add **three new surfaces** on top of L1:

1. **API:** `POST /api/datasets/{id}/preview-clean` (dry-run, returns diff), `POST /api/datasets/{id}/apply` (commit), `GET /api/datasets/{id}/versions`, `POST /api/datasets/{id}/revert`. Keep `POST /api/chat` able to route to cleaning when `planner.intent == "cleaning"` — but also expose explicit wrangling endpoints for UI buttons.
2. **Agent:** Extend `planner` (already detects `cleaning`) + `coder` (add `cleaning_templates` dict). Each template is a tiny `pandas` snippet (e.g., `df['Price'].fillna(df['Price'].median(), inplace=True)`). Add `validator` that checks `result` is DataFrame and diff is sane (no shape explosion).
3. **Storage:** Add `versions/` handling in `storage.py`, atomic writes, `current_version` in `meta.json`. Profiling refreshes on version change.

Reuse `executor.py`/`security.py` — no new sandbox. Add `core/wrangle.py` for helper `diff_dataframes(before, after)`.

## Work Plan (Ordered)

### Unit 2.1 — Storage Versioning (1.5 days)
**Surfaces:** `backend/app/core/storage.py`, `app/config.py`
- [ ] **2.1.1** In `save_dataset`, after initial save, create `versions/0.csv` (copy of `data.csv`) + `versions.json` with `[{version:0, op:"create", prompt:"upload", created_at}]`, set `meta.current_version=0`
- [ ] **2.1.2** Add `list_versions(dataset_id)`, `get_version_path(dataset_id, v)`, `create_version(dataset_id, df, op, prompt, code)` that writes `versions/{v+1}.csv` + updates `versions.json` + `meta.current_version`
- [ ] **2.1.3** Add `revert_to_version(dataset_id, v)` that copies `versions/{v}.csv` → `data.csv` + sets `current_version=v`
- [ ] **2.1.4** Guard storage size: `max_versions=20`; if over, delete oldest (but never v0)
- [ ] **2.1.5** Make all writes atomic (`tmp.json`→`rename`)
**Validation:** `pytest tests/test_storage_versions.py` (create, list, revert, quota).

### Unit 2.2 — Wrangle Helpers & Diff (0.5 day)
**Surfaces:** `backend/app/core/wrangle.py` (new), `app/core/profiling.py`
- [ ] **2.2.1** `wrangle.py`: `diff_dataframes(before, after)` → `{rows_before, rows_after, rows_added, rows_removed, cols_changed, nulls_before/after, dtypes_changed}`
- [ ] **2.2.2** `profiling` already handles post-clean; add `tests/test_wrangle_diff.py`
**Validation:** `pytest tests/test_wrangle_diff.py`.

### Unit 2.3 — Planner & Coder: Cleaning Templates (2 days)
**Surfaces:** `backend/app/agent/planner.py`, `coder.py`, `prompts.py`
- [ ] **2.3.1** Keep `planner` keywords (`remove null`, `duplicate`, `fill`, `drop`) — add `rename`, `convert`, `trim`, `pivot`, `split`, `merge`
- [ ] **2.3.2** In `coder.py`, add `CLEANING_TEMPLATES` branch **before** default fallback, ordered:
  1. `remove duplicates` → `result = df.drop_duplicates()`
  2. `remove duplicates on {col}` → `df.drop_duplicates(subset=['{col}'])`
  3. `fill nulls in {col} with {median|mean|mode|ffill|value}` → `df['{col}'].fillna(...)`
  4. `fill all nulls with {median}` → loop over numeric cols
  5. `drop rows where {col} is null` / `drop rows where {col} == 0` → `df.dropna(subset=...)` or `df.query`
  6. `drop column {col}` → `df.drop(columns=['{col}'])`
  7. `rename {old} to {new}` → `df.rename(columns={'{old}':'{new}'})`
  8. `convert {col} to datetime|numeric|string` → `pd.to_datetime` / `pd.to_numeric`
  9. `trim whitespace in {col}` → `df['{col}'] = df['{col}'].str.strip()`
  10. `standardize case in {col} to lower|upper|title` → `.str.lower()`
  11. `split {col} by {delimiter} into {a, b}` → `df[['{a}','{b}']] = df['{col}'].str.split('{delimiter}', expand=True)`
  12. `remove outliers in {col}` → `df = df[(df['{col}'] - df['{col}'].mean()).abs() < 3*df['{col}'].std()]`
- [ ] **2.3.3** Each template must set `result = df` (the cleaned frame) + optionally `fig = px.bar(nulls...)` for visual; keep `code` without `import`
- [ ] **2.3.4** If `OPENAI_API_KEY` set, allow LLM to **refine** the template (send template code + prompt to LLM for correction), but always fall back to template if LLM fails
- [ ] **2.3.5** Add `tests/test_coder_cleaning.py` with 12 snapshot cases (query+profile→code contains expected snippet)
**Validation:** `pytest tests/test_coder_cleaning.py` + `TestClient` preview for each intent on `employees.csv` and a dirty `test_dirty.csv` (inject nulls, dups).

### Unit 2.4 — API: Preview/Apply/Revert/Versions (1.5 days)
**Surfaces:** `backend/app/api/datasets.py` (new endpoints), `app/services/wrangle_service.py` (new)
- [ ] **2.4.1** `wrangle_service.preview_clean(dataset_id, query)` → load df → `coder` (cleaning branch) → `executor.execute_code` on **copy** → `diff_dataframes` → return `{preview: dataframe_to_json(after.head), diff, code, explanation}`
- [ ] **2.4.2** `POST /api/datasets/{id}/preview-clean {"query": "..."}` → calls `preview_clean` (no save)
- [ ] **2.4.3** `POST /api/datasets/{id}/apply {"query": "...", "code": "..."}` → re-execute code, `create_version`, return new `versions` + updated `profile`
- [ ] **2.4.4** `GET /api/datasets/{id}/versions` → `list_versions`
- [ ] **2.4.5** `POST /api/datasets/{id}/revert {"version": v}` → `revert_to_version`, return new profile
- [ ] **2.4.6** Also wire `POST /api/chat` so when `intent == "cleaning"`, it calls `preview_clean` and returns same shape as normal chat but with `preview` + `diff` fields (so chat UI can show preview without separate call)
**Validation:** `pytest tests/test_api_wrangling.py` (preview, apply, versions, revert, quota).

### Unit 2.5 — Frontend: Clean Tab (1.5 days)
**Surfaces:** `frontend/streamlit_app.py`
- [ ] **2.5.1** Add 4th tab `🧹 Clean` (or 5th if L1 added download): left col = `st.text_input("Describe cleaning (e.g., 'fill missing Price with median')")` + `Preview` button; right cols = `Before (head)` / `After (head)` + `Diff` (`st.metric` for rows/nulls/dtypes) + `Apply` (primary) / `Reset` (secondary)
- [ ] **2.5.2** Below, show `Version History` as `st.dataframe(versions)` + `Undo` selectbox + `Revert` button; after apply/revert, auto-refresh profiling tab
- [ ] **2.5.3** In main `💬 Chat` tab, when chat returns `intent cleaning` + `preview`, show same before/after preview + "Apply this cleaning? [Yes] [No]" inline
- [ ] **2.5.4** Add "Cleaning Examples" sidebar expander with 6 copy-paste prompts
**Validation:** Manual: upload `test_dirty.csv` → Clean tab → `remove duplicates` → Preview shows -2 rows → Apply → Versions goes 0→1 → chat still works → Undo → back to 0.

### Unit 2.6 — Docs & Release (0.5 day)
- [ ] Update `README.md` "Cleaning" section + GIF, `ARCHITECTURE.md` add `wrangle.py` + versioning diagram, `docs/` maybe
- [ ] Tag `v0.2-wrangling`, release notes

**Total: ~7 days (2 weeks)**

## Validation Plan

| Check | Command | Expected |
|-------|---------|----------|
| All tests | `cd backend && /tmp/venv2/bin/python -m pytest tests -q` | 40+ passed |
| Cleaning templates | `pytest tests/test_coder_cleaning.py -v` | 12 snapshots pass |
| Wrangling API | `pytest tests/test_api_wrangling.py -v` | preview, apply, versions, revert all 200 |
| Diff helper | `pytest tests/test_wrangle_diff.py -v` | rows/nulls/dtypes diff correct |
| Security | `pytest tests/test_security.py` | cleaning code still blocked for `os` |
| Manual dirty | Upload `dirty.csv` (10 nulls, 2 dups, `Date` as `12/31/2024`, ` Price` with spaces) → 5 cleaning prompts → each Preview shows correct before/after → Apply → profile updates → Undo works | Visual |
| Chat regression | `python /tmp/e2e_15_queries.py` (L1's 10) | Still 10/10 ✅ |

**Highest-risk:** Wrangling `preview` vs `apply` divergence (preview shows X but apply does Y). Mitigate by re-executing same `code` on apply (don't regenerate).

## Risks / Rollback

| Risk | Mitigation | Rollback |
|------|------------|----------|
| `coder` cleaning templates conflict with L1's `groupby` templates (e.g., "fill nulls in Sales by median" mis-parsed as groupby) | Order cleaning branch **first** before groupby; test `fill` vs `by` disambiguation | Reorder, or split `cleaning` intent to dedicated endpoint (don't use `/api/chat` for cleaning) |
| Version explosion (user spams Apply) | `max_versions=20` quota + `versions.json` size guard | Delete `versions/` manually, reset `current_version` |
| Profiling after cleaning is stale | Re-profile on every `create_version` + `revert` | Call `profile_dataframe` after each storage mutation |
| Streamlit tab adds complexity, breaks layout | Keep tab count ≤5, test on 13" screen | Revert `streamlit_app.py` tab addition |

## Open Questions

- None. Filesystem versioning is proven (simple, no DB). `pandas` covers all 12 intents (tested via `executor`).

---

**Approval Gate:** Reply `Approve` to build Level 2, or `Change` to edit. Do not start Level 3 until this level's validation is green.
