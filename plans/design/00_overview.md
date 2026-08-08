# InsightAgent — Frontend Migration Overview

## Streamlit → vanilla Html / Css / Js

**Target stack:** Tailwind CSS + Alpine.js + Plotly.js, served via Jinja2 templates from FastAPI (`backend/app/main.py`). No React, no Vite, no Streamlit.

**Why:** Streamlit py-rerun model blocks white-label, deep linking, and fine-grained control. FastAPI already serves all data (`/api/datasets`, `/api/chat`, `/api/dashboards`, `/api/connectors`, `/api/schedules`, `/api/auth`, `/api/audit`, `/api/llm/info`). Vanilla stack keeps `docker-compose up` 30s, single binary, and allows neo-minimalist control not possible with Streamlit chrome.

## Design stance — neo-minimalism (non-negotiable)

Applies to every page, every level doc. Whitespaces structures, not boxes. System is flat, hairline, quiet.

- **Flat surfaces only** — no gradients, no drop shadows; only a subtle `0 0 0 2px` focus ring on inputs.
- **Hairline borders** `0.5-1px` (`--border-hairline`) instead of heavy card chrome. `8px` on controls, `12px` on cards (`--radius-control`, `--radius-card`).
- **Whitespace as structure** — `24–48px` section gaps and `16–24px` card padding; never add an extra divider to create hierarchy if spacing already does it.
- **Palette:** ~95% neutrals (white/gray). Exactly **one accent** for primary actions + active states. Separate semantic `danger/success/warning` reserved only for states, never decoration.
- **Typography:** sentence case everywhere, max two weights (`regular 400 + medium 500`), no heavy bold, no all caps.
- **Metric cards:** muted label above, large number below, no border — subtle background tint (`--surface-tint`).
- **Data-dense screens** (tables, audit log, RBAC, connectors): bordered rows, not floating card grids. Scanability over decoration.
- **Icons:** single outline set (Heroicons outline), stroke `1.5`, never filled, never emoji.
- **Charts:** Plotly theme drawn from tokens — accent for primary series, neutrals for grid/axes, never rainbow default.
- **Tokens:** every color/spacing/radius via CSS custom properties (`app/static/css/tokens.css`), never hardcoded hex/px. Rethmeme by editing one file; Tailwind extends from tokens.

This filter also satisfies the anti-AI-slop checklist: no purple/indigo accent, no gradient headlines, no cream page, no aurora glows, no Inter-everywhere, no centered hero + pill + 2 CTAs, no identical 3-card lucide grids, no `rounded-2xl` everywhere, no glassmorphism, no `hover:scale-105`, no emoji icons, no nested cards.

## Scope

All current Streamlit views migrate:
`upload → datasets list → dataset detail (preview/profiling/chat) → dashboards (grid, share ?share=slug) → connectors + join → schedules/reports → Slack events → auth/RBAC/audit → cloud (billing/brand/llm/marketplace) → health/llm info`

Seven design docs define the system before any `.html` is written:

```
plans/design/
  00_overview.md          ← this file
  01_tokens.md            ← CSS custom properties + Tailwind mapping
  02_layout.md            ← shell, nav, whitespace, shell states
  03_components.md        ← controls, metric cards, rows vs cards
  04_charts.md            ← Plotly token theme
  05_pages.md             ← page-by-page Streamlit → Jinja2+Alpine
  06_interactivity.md     ← Alpine stores, fetch, auth, queue polling
  07_migration.md         ← phased cutover, risks, verification
```

No implementation files are created in this phase. Code comes after docs are approved.
