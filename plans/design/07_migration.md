# 07 — Migration Plan (Streamlit → Jinja2)

Cut over without breaking `docker-compose up` or `pytest -q`.

## Phases (sequential, each ends green)

**Phase 0 — Tokens & shell (1d), no behavior change**
- Add `app/static/css/tokens.css` + `tailwind.config.js` extending tokens. No template yet.
- Verify: `grep -r "#[0-9a-f]" app/static --include="*.css"` finds only tokens file.

**Phase 1 — Base template + health (1d)**
- `app/templates/base.html` (top bar 56px, nav accent underline, Jinja2 `__CONFIG` injection). FastAPI `GET /` still serves `{name,version}` JSON; add `GET /app` (or `GET /` when `Accept: text/html`) serving `base.html` with `?demo=1` support. Keep Streamlit on 8501 untouched.
- Verify: `curl -H "Accept: text/html" http://localhost:8000/` returns `<!doctype html>` with `--surface-page` style, no gradient.

**Phase 2 — Datasets (upload/list/detail) (2d)**
- `GET /datasets` → `datasets.html` + `Alpine.store('datasets')` using existing `GET /api/datasets`, `POST /api/datasets/upload`, `GET /api/datasets/{id}` (X-Cache). Migrate `upload → list → profiling` as bordered rows + tint metric cards.
- Dual-run: Streamlit still on 8501, new UI on 8000 (or 8502 during transition). `docker-compose.yml` adds `frontend_v2` service for testing.
- Verify: upload 1M CSV via new UI <2s, profiling KPIs show muted label + large number, no nested expander error.

**Phase 3 — Chat & charts (1.5d)**
- `dataset_detail.html` tab `chat` with Alpine thread + `POST /api/chat` → `202` polling + `Plotly.newPlot` via `plotlyTheme.js`. Replace Streamlit `st.plotly_chart`.
- Verify: `Why did sales drop`, `forecast`, `outliers` render with accent series, grid hairline, no rainbow. Code panel expands via single outline button.

**Phase 4 — Dashboards / share / connectors / join (1.5d)**
- `dashboards.html` grid `12px` cards + `?share=slug` public view; `connectors.html` bordered rows + join flow.
- Verify: pin widget → grid → share link incognito works; join `Region` left produces bordered preview.

**Phase 5 — Schedules / Slack / reports / cloud / audit (1d)**
- Dense admin views as bordered rows (audit, RBAC, schedules, cloud billing). `audit` date-grouped rows, not card grid.
- Verify: admin sees audit rows scanable, viewer cannot delete (403).

**Phase 6 — Cutover (0.5d)**
- `docker-compose.yml` `frontend` now serves FastAPI static (`/app`), Streamlit image kept as `frontend-legacy` profile or removed. `frontend/streamlit_app.py` archived to `frontend/legacy/`. `landing` and `docs` unchanged.
- Verify: `docker-compose up` 30s → `http://localhost:8000/app` or `http://localhost:8501` (new) renders neo-minimalist, `pytest -q` still 156 PASS, `curl /health` ok.

## Routing (FastAPI)

- Serve Jinja2 via `Jinja2Templates(directory="app/templates")` + `StaticFiles(directory="app/static", name="static")`.
- API stays `/api/*`; pages are `/app`, `/app/datasets`, `/app/dashboards`, etc. Content-negotiation on `/` optional; explicit `/app` avoids breaking `/` JSON used by tests.

## Risks / mitigations

- *Streamlit state loss:* Alpine stores + localStorage replace `st.session_state`; audit via manual 15-query smoke (upload → chat 3 → pin → share → connector + join → schedule).
- *Tailwind purge misses Alpine classes:* safelist `x-show`, `x-cloak`; use `tailwind.config.content` globs for `templates/**/*.html`.
- *Plotly FOUC:* `x-init` waits `tokens.css` loaded; `getComputedStyle` fallback to neutrals.
- *Auth:* reuse `app/api/auth.py` JWT; Alpine sends `Authorization: Bearer` — no change.

## Verification gates (each phase)

- `make lint` (now includes `app/templates` html lint), `python -m py_compile` (no Streamlit import in new code), `pytest -q` (backend unchanged).
- Manual: 20s GIF flow (upload → chat → pin → share) works for incognito on new UI.
- Visual: screenshot shows >95% white/gray, one accent pixel, hairline borders, `8px/12px` radii, outline icons, no gradient/shadow.

## Out of scope for migration

- No new backend endpoints (reuse all).
- No rewrite of `landing` (Vite) or `docs` (Docusaurus).
- No implementation files in this phase — docs only; code starts after approval.
