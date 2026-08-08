# Level 3 — Dashboard Studio: From Chat to Shareable Dashboard (OSS)

> **Pin any chart, arrange, filter, share a link. No BI tool needed.**

---

## Goal

Turn one-off chat charts into **persistent, shareable dashboards**. After Level 3, you can select 4-6 chat outputs, click **Pin to Dashboard**, arrange in a grid, add title/filters, save, get a **public share link** (`/d/{slug}`) and **embed iframe**, with live data (reads current `data.csv`).

## Success Criteria

- [ ] In chat, each chart has **📌 Pin** button; pinning adds a `widget` to a `dashboard` (linked to `dataset_id`)
- [ ] Dashboard Studio page/tab: grid (2-col) of widgets, each widget shows `title`, `chart` (Plotly), `result` (table), `query` (caption), `refresh` (re-run code on current data) and `remove`
- [ ] Dashboard has **Save** (`name`, `description`), **List** (`GET /api/dashboards`), **Open**, **Duplicate**, **Delete**
- [ ] **Public share**: `GET /api/dashboards/{id}/share` → `{slug}`, `GET /d/{slug}` renders read-only dashboard (no auth, no code execution beyond stored `result`+`chart`); share can be **revoked** (regen slug or set `is_public=false`)
- [ ] **Filters:** Dashboard-level `dropdown` filter on any categorical column (e.g., `Region`, `Category`) that re-filters all widgets' `result` tables client-side (L3) or via re-execution (stretch, L4)
- [ ] **Export:** `GET /api/dashboards/{id}/export?format=pdf|png` returns static PDF (via `plotly.io` + `reportlab` or screenshot) — at least CSV of all widgets
- [ ] Widgets are **snapshots** in L3: pin stores `chart_json` + `result_json` at pin time; `Refresh` re-runs stored `code` on current `data.csv` to update (shows staleness badge if data version ≠ widget version)
- [ ] `pytest` 50+ tests (add 10), `py_compile` clean, `docker-compose up` still works, no regression on L1/L2 chat
- [ ] README adds Dashboard GIF + share link demo

## Context & Current Facts

**L2 delivered:**
- Dataset versioning (`versions/{v}.csv`), cleaning preview/apply/revert, wrangling templates, `core/wrangle.py`, `api/datasets/preview-clean`.
- `storage` now has `datasets/{id}/data.csv` + `versions/` + `meta.json` (`current_version`). Profiling refreshes.
- `executor` is hardened, `coder` is deterministic, `planner` is heuristic+LLM.

**Pain:** Users get a chart in chat but can't keep it. They screenshot. Next day data changes, screenshot is stale. They want a Notion/Mode-style dashboard they can share with boss without giving raw data access.

## Constraints & Non-Goals

**Constraints:**
- Stay MIT, no auth yet (L7), no DB connectors yet (L4)
- No new DB — keep filesystem (`storage/dashboards/{id}.json`)
- Keep Streamlit (add tab/page, not Next.js)
- Pin must be **instant** (<200ms, no LLM)

**Non-Goals (for L3):**
- No real-time websocket (polling is fine)
- No role-based sharing (link = anyone with link; L7 adds RBAC)
- No pixel-perfect layout builder (grid is enough; free-drag in L6/white-label)
- No cross-dataset dashboard (one `dataset_id` per dashboard in L3; multi in L4)

## Key Decisions

| Decision | Recommended | Why |
|----------|-------------|-----|
| **Dashboard storage** | Filesystem `storage/dashboards/{dash_id}.json` + `storage/dashboards/{share_slug}.json` index; each file: `{id, dataset_id, name, description, created_at, is_public, share_slug, widgets: [{id, query, code, result, chart, title, created_at, dataset_version}]}` | Alt: DB adds ops; file is simple, portable, fits OSS self-host; `dashboards/` is scan-fast (<1k dashboards) |
| **Widget content** | Snapshot `result`+`chart` at pin time + stored `code`+`dataset_version` for refresh | Alt: live re-execution on every view is slow/expensive; snapshot is instant, refresh is explicit (user controls cost) |
| **Share link** | Random `slug` (8-char `secrets.token_urlsafe`) in `dashboards/{id}.json` (`share_slug`), public route `GET /api/dashboards/share/{slug}` returns dashboard JSON without requiring dataset access; frontend at `/d/{slug}` renders read-only | Alt: signed JWT overkill for OSS; slug is simple, revocable by regen |
| **Frontend layout** | Streamlit: new page `📊 Dashboards` in sidebar (list + create), and `Dashboard Studio` tab inside dataset view when at least 1 chat chart exists; grid via `st.columns(2)` + `st.plotly_chart` | Alt: `Next.js` + `react-grid-layout` is better but doubles L3 time; Streamlit grid proves value, can swap in L8 premium |
| **PDF export** | L3 ships `CSV` export of all widget results (zip) + `JSON` of dashboard; PDF/PNG is **stretch** via `plotly.io.write_image` (needs `kaleido` + 100MB) — defer heavy PDF to L6 if kaleido is too big | Alt: full PDF in L3 adds heavy dep; CSV is useful now |
| **Refresh** | `POST /api/dashboards/{id}/widgets/{wid}/refresh` re-executes stored `code` on current `data.csv` via `executor`, updates `result`/`chart`/`dataset_version`, returns new widget | Alt: auto-refresh on dashboard open is confusing; explicit button is predictable |

## Recommended Approach

Add **two new surfaces**: `api/dashboards.py` + `services/dashboard_service.py`, and **frontend**: dashboard list + studio + public share.

Reuse `storage.py` pattern, `executor` for refresh, `profiling` not needed. Keep `POST /api/chat` pin as client-side (frontend extracts `result`+`chart` from chat response and posts to `api/dashboards`).

### Data Flow

```
Chat → Pin (frontend) → POST /api/dashboards {dataset_id, name} → dash_id
                    → POST /api/dashboards/{id}/widgets {query, code, result, chart}
Dashboard Studio ← GET /api/dashboards?dataset_id=... ← storage/dashboards/*.json
Share → POST /api/dashboards/{id}/share → {slug} → GET /api/dashboards/share/{slug} (public)
Refresh → POST /api/dashboards/{id}/widgets/{wid}/refresh → executor(code, current df) → updated widget
```

## Work Plan (Ordered)

### Unit 3.1 — Dashboard Storage & Service (1.5 days)
**Surfaces:** `backend/app/core/storage.py` (add dashboard helpers), `app/services/dashboard_service.py` (new)
- [ ] **3.1.1** Add `storage/dashboards/` helpers: `_dashboards_dir()`, `save_dashboard(dash)`, `get_dashboard(dash_id)`, `list_dashboards(dataset_id?)`, `delete_dashboard(dash_id)`, `get_by_slug(slug)`, `generate_slug()` (8-char, collision check)
- [ ] **3.1.2** `dashboard_service.create_dashboard(dataset_id, name, description)` → `id=uuid4[:8]`, `widgets=[]`, `is_public=false`, `share_slug=None`
- [ ] **3.1.3** `add_widget(dash_id, widget)` where `widget={id: uuid4[:6], query, code, result, chart, title, dataset_version: current_version, created_at}`
- [ ] **3.1.4** `refresh_widget(dash_id, wid)` → `load_dataset_df(dataset_id)` → `executor.execute_code(stored_code, df)` → update `result`/`chart`/`dataset_version` → `save_dashboard`
- [ ] **3.1.5** `share_dashboard(dash_id)` → if `is_public && slug` return existing, else `slug=generate_slug()` + `is_public=true` + save; `unshare(dash_id)` → `is_public=false`
- [ ] **3.1.6** Atomic writes (`tmp.json`→`rename`), `max_dashboards_per_user=50` (hard cap)
**Validation:** `pytest tests/test_storage_dashboards.py` (create, add, refresh, share, delete).

### Unit 3.2 — API: Dashboards (1 day)
**Surfaces:** `backend/app/api/dashboards.py` (new), `app/main.py` (include router)
- [ ] **3.2.1** `POST /api/dashboards {dataset_id, name, description?}` → create
- [ ] **3.2.2** `GET /api/dashboards?dataset_id=` → list (filter), `GET /api/dashboards/{id}` → get (with widgets)
- [ ] **3.2.3** `POST /api/dashboards/{id}/widgets {query, code, result, chart, title?}` → add_widget (title defaults to `query[:40]`)
- [ ] **3.2.4** `DELETE /api/dashboards/{id}/widgets/{wid}` → remove
- [ ] **3.2.5** `POST /api/dashboards/{id}/widgets/{wid}/refresh` → refresh_widget
- [ ] **3.2.6** `POST /api/dashboards/{id}/share` → `{slug, url: "/api/dashboards/share/{slug}"}`, `DELETE /api/dashboards/{id}/share` → unshare
- [ ] **3.2.7** `GET /api/dashboards/share/{slug}` → public (no auth, returns dashboard JSON)
- [ ] **3.2.8** `GET /api/dashboards/{id}/export?format=csv|json` → CSV zip (one file per widget `result`) or JSON dump; PDF stretch: `GET ...?format=pdf` if `kaleido` present else 501
**Validation:** `pytest tests/test_api_dashboards.py` (create, add 2 widgets, refresh, share, export, delete).

### Unit 3.3 — Frontend: Dashboards List + Studio (2 days)
**Surfaces:** `frontend/streamlit_app.py`
- [ ] **3.3.1** In sidebar, add `📊 Dashboards` section: `list_dashboards()` + `Create New Dashboard` (name input) + `Open` buttons; when a `dataset_id` is selected, filter to that dataset's dashboards
- [ ] **3.3.2** In `💬 Chat` tab, after each chart+table, add `📌 Pin to Dashboard` button: shows `selectbox(dashboards)` + `Pin` (posts to `POST .../widgets`); on success `st.toast("Pinned!")`
- [ ] **3.3.3** New top-level tab/page `📊 Dashboard Studio` (when at least 1 dashboard exists): 
  - Header: `dashboard.name` + `description` + `Share` (generates slug, shows `st.code(public_url)`) + `Export CSV` + `Delete`
  - Grid: `st.columns(2)` loops `widgets`, each card: `title` (editable `st.text_input`), `st.plotly_chart(chart)`, `st.dataframe(result)`, `caption(query)`, `Refresh` + `Remove` buttons, staleness badge `if widget.dataset_version != current_version → "⚠️ Data updated, click Refresh"`
- [ ] **3.3.4** Public share view: new Streamlit page `pages/share.py` or query param `?share=slug` that calls `GET /api/dashboards/share/{slug}` and renders read-only grid (no pin/refresh/delete)
- [ ] **3.3.5** Filter (MVP): add `st.selectbox("Filter by", categorical_columns)` + `st.multiselect(values)` at top of Studio; filter is **client-side** (pandas `df[result][col].isin(values)`) for L3, not re-execute
**Validation:** Manual: chat 2 queries → pin both to "Sales Dashboard" → open Studio → see 2 cards in grid → click Refresh → see staleness cleared → Share → open incognito `/d/{slug}` → see read-only → Export CSV → download zip → Delete widget → Delete dashboard.

### Unit 3.4 — Polish & Tests (1 day)
- [ ] Add `tests/test_dashboard_refresh_stale.py` (create version after pin, staleness badge)
- [ ] Handle empty dashboard: show "No widgets yet, go to Chat and Pin"
- [ ] Handle large dashboard: paginate widgets (show 6, `Load more`)
- [ ] Update `README.md` + `ARCHITECTURE.md` (dashboard storage diagram)
**Validation:** `pytest -q` (50+ total), `py_compile`, manual share.

### Unit 3.5 — Docs & Release (0.5 day)
- [ ] Tag `v0.3-dashboard`, GIF, release notes

**Total: ~6 days (2-3 weeks)**

## Validation Plan

| Check | Command / Manual | Expected |
|-------|------------------|----------|
| All tests | `cd backend && pytest tests -q` | 50+ passed |
| Dashboard storage | `pytest tests/test_storage_dashboards.py -v` | create/add/refresh/share |
| Dashboard API | `pytest tests/test_api_dashboards.py -v` | all endpoints 200 |
| Pin flow | `TestClient` script: upload → chat → pin 2 → list → share → public get | 200 at each step, `share_slug` present |
| Refresh + staleness | Upload → pin → clean (new version) → Studio shows ⚠️ → Refresh → ⚠️ gone + result updated | Visual |
| Share revoke | Share → GET public 200 → DELETE share → GET public 404 | — |
| Export | `GET /api/dashboards/{id}/export?format=csv` → zip with 2 CSVs | — |
| Frontend | Manual pin → studio grid → share incognito → export | Works |
| Regression | `python /tmp/e2e_15_queries.py` + `tests/test_wrangling*` | Still green |

**Highest-risk:** Public share without auth leaks data. Mitigate: dashboard `result`+`chart` are **snapshots**, not live `df`; slug is random 8-char, not guessable; `unshare` revokes. In L7, add optional `is_public` flag off by default.

## Risks / Rollback

| Risk | Mitigation | Rollback |
|------|------------|----------|
| `st.columns(2)` grid breaks on mobile | Test on 375px width, fallback to 1-col if `st.columns` fails | Revert to `st.container` vertical stack |
| Widget `result` large (10k rows) blows `dashboards/*.json` (size >1MB) | Store `result` truncated to 100 rows (`dataframe_to_json` already truncates), full data via re-execution | Truncate, add `full_result_url` later |
| Share slug collision | Loop until unique, check existing slugs | Regenerate |
| `Refresh` runs arbitrary stored `code` — need re-validation | Re-run `validate_code` on stored `code` before refresh | Block if `SecurityError` |

## Open Questions

- None. Filesystem dashboards proven (Cal.com does similar). Streamlit `pages/` for public share is L3 choice; can keep in main app via query param if `pages/` is heavy.

---

**Approval Gate:** Reply `Approve` to build Level 3, or `Change` to edit. Do not start Level 4 until validation green.
