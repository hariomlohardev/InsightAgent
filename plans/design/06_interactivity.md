# 06 — Interactivity & State (Alpine.js)

Streamlit reruns disappear. State lives in Alpine stores + `fetch`; Jinja2 renders shell only.

## Alpine choice

Alpine `3.x` via CDN `defer`, no build step. One `app.js` for stores, rest is `x-data` inline. No React, no heavy bundling.

## Stores (single source)

- `Alpine.store('auth', { token, user, role, login(), logout() })` — persists `localStorage`, adds `Authorization: Bearer` to fetch. `AUTH_REQUIRED` flag from Jinja2 `window.__CONFIG`.
- `Alpine.store('datasets', { list, selectedId, fetchList(), upload() })` — poll list after upload.
- `Alpine.store('chat', { messages, jobId, send(), poll() })` — handles `202 → GET /api/jobs/{id}` loop.
- `Alpine.store('dashboards', { ... })`, `store('connectors')`, `store('toasts')`.

No global `window` vars; no duplicated `fetch` per component.

## Fetch pattern

All data via `fetch` to existing FastAPI `api/*` (no new endpoints needed). Example flow (dataset list) — conceptual, not implemented:

- `GET /api/datasets` → store list → render rows via `x-for`.
- `POST /api/datasets/upload` with `FormData` → on 200, `store.datasets.fetchList()` + toast `success`.

Error: single toast `12px` hairline, `13px`, `danger` left border, not per-field inline explosion.

## UI bindings

- `x-data="{ tab: 'preview', query: '' }"` for dataset detail tabs; active underline `accent` 2px via `:class`.
- `x-show` for code expander, not nested `<details>` inside expanders.
- `@click` on primary buttons → `store.chat.send()` → optimistic user bubble, then assistant card.

## Auth & RBAC

- Jinja2 injects `__CONFIG.authRequired` (bool). Alpine guards: `x-show="auth.role==='admin'"` for audit. Viewer gets disabled `delete` (ghost, `disabled`, `title` sentence case `read-only`).

- No second login form when already authenticated; store drives `x-if`.

## Queue polling

Forecast/large `POST /api/chat` → `202 {job_id}` → Alpine `setInterval 1000ms ×20` `GET /api/jobs/{id}` → on `completed`, render result/chart. On `failed`, toast `danger`. Uses `store.chat.poll()`, not Streamlit `st.spinner` blocking.

## Charts

`x-init="renderPlot(el, chartJson)"` where `renderPlot` reads tokens via `getComputedStyle` and calls `Plotly.newPlot(el, data, layout, {responsive:true, displayModeBar:false})`. Debounced resize `150ms`.

## File structure (planned, not created)

```
app/
  templates/
    base.html               # shell, top bar, tokens link, Alpine+Plotly CDN
    pages/
      datasets.html
      dataset_detail.html
      dashboards.html
      connectors.html
      schedules.html
      cloud.html
  static/
    css/tokens.css
    css/app.css             # Tailwind @layer using tokens
    js/app.js               # Alpine stores
    js/plotlyTheme.js
```

## No-go

- No `hover:scale`, no scroll `fade-up`, no glassmorphism, no emoji.
- Max one `setInterval` per store; clear on `x-destroy`.
- Respect `prefers-reduced-motion` — no motion if set.

## Verification

- Disconnect backend (`BACKEND_URL` bad) → `_try_get` fallback still shows `backend not reachable` hairline banner + retry, not 500.
- No `import` in generated code path still validated via `validate_code`; UI just displays code panel.
