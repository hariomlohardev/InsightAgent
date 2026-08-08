# InsightAgent — 8-Level Build Roadmap (Full OSS → Full Product)

**Goal:** Build a complete AI Data Analyst platform in 8 incremental levels. Each level is a shippable, testable slice. You finish Level N with a working, better product before starting N+1. By Level 8 you have **100% of the vision**: ingestion → cleaning → dashboards → connectors → deep analytics → automation → enterprise → cloud/billing.

**Principle:** Levels 1-6 are **100% MIT open-source**. Levels 7-8 add **open-core + paid cloud** (premium is hosting, SSO, billing, white-label — core stays MIT). This matches `n8n / PostHog / Cal.com` model that users trust.

---

## The 8 Levels at a Glance

| Level | Name | One-Line | OSS? | Build Time | Ships What |
|-------|------|----------|------|------------|------------|
| **1** | **Foundation** — Ingestion, Profiling, Chat Core | Make the MVP rock-solid | ✅ MIT | 2 wks | Polished ingestion (CSV/Excel/JSON), profiling, chat→code→chart, insights, tests, Docker, docs |
| **2** | **Wrangling Agent** — Cleaning & Transform | "Fix my data" in English | ✅ MIT | 2 wks | Null handling, dedup, type coercion, rename, pivot/melt, natural-language transforms with preview & undo |
| **3** | **Dashboard Studio** — Drag-Drop & Sharing | From chat to shareable dashboard | ✅ MIT | 2-3 wks | Pin charts to dashboard, layout, filters, public share link, embed |
| **4** | **Universal Connectors** — Live Data & Joins | Connect anything, join everything | ✅ MIT | 3 wks | Postgres/MySQL/BigQuery/SQLite, Google Sheets, API, multi-file JOIN, DuckDB federation |
| **5** | **Deep Analytics** — Stats, Outliers, Forecast | Answer "why" and "what next" | ✅ MIT | 3 wks | Correlation, outlier detection, cohort/segment, Prophet/StatsForecast, what-if |
| **6** | **Automation & Collaboration** — Reports & Team | Reports that run themselves | ✅ MIT | 2-3 wks | Scheduled PDFs, Slack/Discord/Email bots, comments, report builder, export |
| **7** | **Enterprise Hardening** — Scale, Security, Quality | Ready for 1k users, 100M rows | ✅ OSS + paid SSO | 3 wks | Auth/RBAC, API keys, audit log, Redis cache, Celery queue, 10x perf, 90% coverage |
| **8** | **Cloud & Business** — Monetize | Turn OSS into revenue | Open Core (MIT core + paid cloud) | 3-4 wks | Billing (Stripe), multi-tenant cloud, white-label, local LLM, marketplace, landing page |

**Cumulative Flow:**
```
L1 (ingest+chat) → L2 (clean) → L3 (dashboard) → L4 (live data) → L5 (forecast) → L6 (automate) → L7 (harden) → L8 (monetize)
```

---

## How to Use This Roadmap

1. **Pick a level** (start at 1, don't skip). Each `plans/LEVEL_XX_*.md` is decision-complete — read it, approve, then build.
2. **Build only that level** — its `Work Plan` is ordered; do tasks top→bottom.
3. **Validate** with its `Validation Plan` (pytest + manual checks). If validation fails, don't start next level.
4. **Commit per level** as a single PR / tag (`v0.1` → `v0.8`). Keeps history reviewable.
5. **Levels 1-6** you can ship fully OSS on GitHub. **Level 7** adds enterprise flags (behind `ENTERPRISE=true`). **Level 8** adds `cloud/` service that you charge for.

## Dependency Graph

```
L1 ──► L2 ──► L3 ──► L4 ──► L5
                │      │
                └──────► L6 ──► L7 ──► L8
```
- L3 needs L2's clean data (dashboards on dirty data are useless).
- L4 unlocks L5/L6 (live data → forecast/automation).
- L7 must come after all features (hardening without features is wasted).
- L8 is last (needs stable product to sell).

## Definition of OSS vs Premium

| Layer | OSS (MIT) | Premium (Cloud/Enterprise) |
|-------|-----------|----------------------------|
| All features L1-L6 | ✅ full | ✅ hosted with support |
| SSO (Google, SAML), RBAC, Audit | flag + self-host | hosted, managed |
| Billing, multi-tenant, white-label | ❌ (docs only) | ✅ paid |
| Local LLM (Ollama) | ✅ self-host | ✅ one-click |
| Priority support | community | ✅ SLA |

No feature is **removed** from OSS to force payment — premium is **convenience + scale**.

## Success Criteria (After L8)

- [ ] Any user can upload CSV/Excel or connect Postgres/Sheets in <60s
- [ ] Clean, dashboard, forecast, schedule — all from chat — no code needed
- [ ] 10M-row CSV queries in <3s (DuckDB + cache)
- [ ] 90% test coverage, 100% of chat paths covered by executor tests
- [ ] Docker-compose up, public share link, PDF report, Slack bot all work
- [ ] Cloud at $19/$49/$499 tiers with Stripe, OSS stars >500

## What You Already Have (Ground Truth 2025-08-08)

- `backend/app/main.py`, `api/datasets.py`, `api/chat.py`, `agent/(planner|coder|executor|explainer)`, `core/(profiling|storage|security)` — all working
- Frontend `streamlit_app.py` with chat, preview, profiling_tabs
- `sample_data/sales.csv` (24 rows) + `employees.csv`
- `/tmp/venv2` proves `17/17` pytest pass, 10/10 chat patterns pass
- `.git` is read-only in this sandbox (commit blocked) — run `git init` locally
- `storage/` is gitignored, resolved to `PROJECT_ROOT/storage` via `config.py`

## File Map

```
plans/
  00_ROADMAP.md            ← you are here
  01_LEVEL_01_FOUNDATION.md
  02_LEVEL_02_WRANGLING.md
  03_LEVEL_03_DASHBOARD.md
  04_LEVEL_04_CONNECTORS.md
  05_LEVEL_05_ANALYTICS.md
  06_LEVEL_06_AUTOMATION.md
  07_LEVEL_07_ENTERPRISE.md
  08_LEVEL_08_CLOUD.md
docs/ or specs/ (optional) can mirror plans/ for GitHub Pages
```

## Execution Rules

- **One level at a time**, in order. Don't parallelize levels.
- Each level ends with a **demo GIF + release notes** in README.
- If a level's validation fails, fix before moving on.
- Keep `main` green — `pytest` must stay 17+ → 100+ tests by L8.

---

**Next:** Open `plans/01_LEVEL_01_FOUNDATION.md` and build Level 1. When Level 1's `Validation Plan` is green, come back and pick Level 2.

**Approval Gate:** Reply `Approve` to start Level 1, or `Change` to adjust this roadmap.
