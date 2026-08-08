# 05 — Pages (Streamlit → Jinja2 + Alpine)

Each page: FastAPI `GET /page` → `templates/pages/<name>.html` extending `base.html`, with an Alpine component driving fetch to existing `api/*`. No Streamlit import.

Sentence case, whitespace-first, same shell.

## `/` datasets (lists + upload)

**Was:** Streamlit uploader + live list + profiling tabs.

**Now:** Header `Datasets` + muted `3 datasets, 1.2M rows`. Primary `Upload dataset` (accent) top-right.

- Upload area: dashed `0.5px` hairline `12px` card `padding 24`, not heavy dropzone. Outline `upload` icon + `drop csv, excel or json` `14px` + `browse` ghost button. Progress via Alpine `fetch` streaming (existing upload API).

- Dense list: bordered rows (03_components) — columns: `name` `rows` `created` `actions`. Name `500`, rows `tabular-nums` `13px text-secondary`. No card grid.

- Empty: tinted metric-style hint + upload CTA.

## `/datasets/{id}` detail

Tabs become Alpine `x-data="{tab:'preview'}"` with underline active (accent 2px), not Streamlit `stTabs` pill.

- `preview`: bordered rows table `10 rows`, `font 13px`, horizontal scroll, not `st.dataframe` chrome.
- `profiling`: left muted labels (`nulls`, `unique`) `12px`, right large numbers — tint cards for KPIs; then column details in bordered rows (hairline).
- `chat`: see below.

## Chat (embedded in dataset, also `/chat?dataset_id=`)

**Was:** `st.chat` + spinner + code expander.

**Now:** Minimal thread:

- User bubble: `surface-muted` `8px` `14px` left-aligned, no avatar pill.
- Assistant: white card `12px` hairline + `insight` bullets `14px`, then `result` table (bordered rows) then `Plotly` chart. No shadow.

- Code/details: single `show code` outline button expands hairline panel, not nested expanders.

- Queue state (forecast >1M → `202 {job_id}` → `GET /api/jobs/{id}`): Alpine polls `1s` ×20, shows `queued` muted badge + `accent` spinner outline.

## Dashboards `/dashboards`

- List: bordered rows — `name` `dataset` `widgets` `updated`, `Share` ghost + `Open` secondary.

- Detail: 2-col grid on desktop `gap 16`, single col mobile. Widgets are `12px` hairline cards with `title 500` + `Q:` caption + table (bordered rows) + chart. No `widget-card` shadows.

- Create: `12px` card modal (not Streamlit sidebar), inputs `8px`, primary `Create`.

- Share `?share=slug` public view: same shell without nav, top bar shows `shared dashboard` + `Back to app` ghost. No auth chrome.

## Connectors `/connectors` + join

- Connector list: bordered rows — `name` `kind` `table` `status` dot `success/danger` semantic.

- `New connector` form: `8px` inputs, hairline.

- `POST /api/datasets/join` result: row preview + new dataset id, not floating grid.

## Schedules / reports / Slack

- Schedules: bordered rows — `cron` `channel` `next run` `status`. threshold alert uses `warning` semantic only for warning.

- Slack/ Reports: same row pattern; no emoji icons; outline `slack`/`file` icons.

## Auth / RBAC / audit (enterprise)

- **Auth:** centered `400px` card (hairline, `12px`) when `AUTH_REQUIRED`, sentence case `Email`, `Password`. No double login.

- **RBAC settings:** users table — bordered rows `email` `role` `actions` (select `8px`). Header `Manage roles` `18px 500`.

- **Audit log:** date-grouped bordered rows, `12px` `at · user · action · dataset_id` — scanable list, not cards.

## Cloud `/cloud` (billing/brand/llm/marketplace)

- Billing: metric cards (tint, no border) for `plan`, `usage`, `quotas` → bordered rows for invoices. `Upgrade` accent.

- Brand: left form (inputs `8px`) + right live preview hairline card — not gradient preview.

- Marketplace: templates as bordered rows with `Install` secondary, not 3-card feature grid with lucide squares.

## Health / llm

Top bar LLM badge uses accent/neutral only (no per-provider rainbow). `GET /health` + `GET /api/llm/info` remain JSON; UI shows `heuristic` muted.

## Common page rules

- One primary action per page, accent. Others secondary/ghost.
- All tables remain tables on mobile (scroll), never reflow to cards.
- No page uses more than ~5% accent pixels.
