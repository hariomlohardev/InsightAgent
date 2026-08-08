# Level 8 — Cloud & Business: Turn OSS into Revenue (Open Core)

> **OSS got you stars. Cloud gets you paid.**

---

## Goal

Monetize without closing OSS. After Level 8, you have **insightagent.com** (or your domain) — a **multi-tenant cloud** where teams sign up, pay $19/$49/$499, get a hosted `app.insightagent.com` + custom domain, white-label, and local LLM, while **core stays MIT** on GitHub.

## Success Criteria

- [ ] **Landing + Auth:** `landing/` (Next.js or pure HTML) with pricing, demo GIF, `Sign up` → `POST /api/cloud/auth/register` → email verification (mock) → `workspace` created (`storage/workspaces/{ws_id}/...` isolated per tenant)
- [ ] **Multi-tenant:** Every `dataset`, `dashboard`, `schedule` is scoped to `workspace_id` (from JWT `ws_id`); `GET /api/datasets` only returns own workspace's; `storage/workspaces/{ws_id}/datasets/` filesystem isolation; admin can still run self-host without cloud (single workspace `default`)
- [ ] **Billing:** `Stripe` (`stripe==7.8`) `POST /api/cloud/billing/checkout {plan: pro|team|enterprise}` → Stripe Checkout → `webhook` → `storage/workspaces/{ws_id}/billing.json` (`plan`, `stripe_customer_id`, `status`); `GET /api/cloud/billing` shows plan + usage (`datasets`, `schedules`, `rows`); `middleware` enforces quotas (`free: 3 datasets, 50 queries/mo, 1 user` vs `pro: unlimited` etc per `00_ROADMAP.md`); `tests/test_billing_mock.py` mocks Stripe
- [ ] **White-label:** `POST /api/cloud/workspaces/{id}/brand {logo_url, primary_color, app_name}` → stored in `workspaces/{ws_id}/brand.json` → frontend reads `brand` and applies CSS + title; `enterprise` plan only
- [ ] **Local LLM:** `POST /api/cloud/llm/set {provider: openai|ollama, model: gpt-4o-mini|llama3}`; if `ollama`, backend calls `http://ollama:11434/api/generate` (Docker `ollama` service) so data never leaves; `OPENAI_API_KEY` per workspace (BYOK) stored encrypted (or plain for OSS, warn)
- [ ] **Marketplace (MVP):** `storage/marketplace/{id}.json` with 10 pre-made agents (`Market Research`, `Invoice Parser`, etc) + `POST /api/marketplace/{id}/install` → clones `dashboards`+`queries` into `workspace`
- [ ] **Admin Panel:** `GET /api/cloud/admin/stats` (admin only) → `{total_workspaces, mrr, active schedules}` for founder
- [ ] `pytest` 100+ tests (add 10), `py_compile` clean, `README` adds `insightagent.com` link + `CLOUD.md` docs, `docker-compose.cloud.yml` with `landing` + `ollama`
- [ ] **No OSS regression:** `docker-compose up` without `STRIPE_KEY` still boots **self-host OSS** as `default` workspace, no billing check

## Context & Current Facts

**L7 delivered:**
- Enterprise hardening (JWT/RBAC/audit), perf (Polars/Redis/cache), queue (Celery), S3, 90+ tests, coverage 90%.

**Pain:** OSS users love it but ask "Can you host it? I don't want to run Docker". Individual won't pay, teams will. Need `mrr`.

## Constraints & Non-Goals

**Constraints:**
- **Open core:** `core MIT` must stay buildable without Stripe/cloud. Cloud is a **separate service** `cloud/` that mounts same `backend` but adds `cloud/` module + `landing/`. `git` history shows `cloud/` is new folder, not a rewrite.
- Keep `stripe` mockable (no real charge in CI)
- Keep `ollama` optional (10GB image, not in default `up`)
- No new DB — keep filesystem per-workspace (`storage/workspaces/{ws_id}/...`)

**Non-Goals (for L8):**
- No mobile app
- No desktop app
- No SOC2 audit docs (post-L8)
- No per-seat billing proration complexity — flat $19/$49/$499

## Key Decisions

| Decision | Recommended | Why |
|----------|-------------|-----|
| **Multi-tenant isolation** | `workspace_id` in JWT + filesystem `storage/workspaces/{ws_id}/` (each has `datasets/`, `dashboards/`, `schedules/`); `storage.py` `get_storage_path()` now returns `.../workspaces/{ws_id}/` when `CLOUD=true`, else `.../storage/` | Alt: Postgres schema per tenant is heavier; filesystem per-workspace is simple, portable, backup via `tar` |
| **Billing** | `Stripe` Checkout + `webhook` → `billing.json`; `stripe-cli` for local dev; quotas enforced in `api` middleware (if `free` and `datasets>3` → 402) | Alt: `Paddle`/`Lemonsqueezy` are alternatives but Stripe is standard, docs abundant |
| **White-label** | `brand.json` per workspace (`logo`, `color`, `app_name`), frontend `st.markdown(f"<style>:root{{--primary:{color}}")` + `st.set_page_config(page_title=brand.app_name)`; enterprise flag checks `plan` | Alt: full CSS theming needs Next.js; Streamlit `st.markdown(style)` is enough for L8 |
| **Local LLM** | `ollama` Docker service (`ollama/ollama:0.3`, `model: llama3.1:8b` or `qwen2.5:7b`); `agent/coder.py` already has `OPENAI_API_KEY` check → add `OLLAMA_URL` fallback; per-workspace `llm.provider` stored in `workspaces/{ws_id}/llm.json` | Alt: self-host `vLLM` is heavier (needs GPU); Ollama runs on CPU, 8GB RAM, fine for BYOK |
| **Landing** | `landing/` as static `Next.js` or `Vite` + `Tailwind` (3 pages: `/`, `/pricing`, `/docs`), links to `app.insightagent.com` (which is just `frontend` with `CLOUD=true`); or even `landing/README.md` + `CNAME` for L8 MVP (ship faster) | Alt: no landing is bad for conversion; static 3-page is 1 day, worth it |
| **Marketplace** | File `storage/marketplace/market_research.json` with `{queries, dashboard_template}`; `POST /api/marketplace/{id}/install` copies to workspace | Alt: full app store needs review; file-based is enough for 10 templates |
| **Domain** | Cloud runs as `app.insightagent.com` + `*.insightagent.com` for white-label `custom.insightagent.com` via `Caddy` or `Traefik` with `CADDY_TLS=internal` for dev | Alt: custom domain per workspace is enterprise only; L8 MVP can be just `app.` |

## Recommended Approach

Add **new top-level** `cloud/` and `landing/` that **reuse** `backend/` and `frontend/` without forking.

### Cloud Architecture

```
Browser → landing.insightagent.com (Next.js, pricing, signup)
        → app.insightagent.com (frontend Streamlit with CLOUD=true → shows workspace switcher, billing)
        → api.insightagent.com (backend with CLOUD=true → checks workspace_id, quotas, billing)
                ↘ storage/workspaces/{ws_id}/datasets|dashboards|schedules
                ↘ Stripe (checkout, webhook)
                ↘ Ollama (local LLM)
                ↘ S3 (if needed, from L7)
Self-host → docker-compose up (CLOUD=false) → single workspace `default`, no billing, MIT
```

Keep `backend/app/config.py` `CLOUD=false` default; when `CLOUD=true`, `get_storage_path()` + `get_current_user()` also load `workspace_id`.

### Data Flow

```
Signup → POST /api/cloud/auth/register {email, pass, workspace_name} → create workspace/{id}/ + user + send verification → JWT with ws_id
Billing → POST /api/cloud/billing/checkout {plan} → Stripe → redirect → webhook → billing.json + plan upgrade → quota lifted
Chat → same as L1 but with workspace scoping + quota check (if free and queries>50/mo → 402)
Branding → GET /api/cloud/workspaces/{id}/brand → frontend applies CSS
Marketplace → GET /api/marketplace → list → POST /api/marketplace/{id}/install → clone dashboard
```

## Work Plan (Ordered)

### Unit 8.1 — Workspace Isolation (1.5 days)
**Surfaces:** `backend/app/core/storage.py`, `app/config.py`, `app/core/auth.py`, `app/api/auth.py`
- [ ] **8.1.1** Add `CLOUD=false` in `config.py`; when `true`, `get_storage_path()` returns `PROJECT_ROOT/storage/workspaces/{ws_id}/` where `ws_id` from `request.state.user.workspace_id` (via `ContextVar`); when `false`, keep `PROJECT_ROOT/storage/` (back-compat)
- [ ] **8.1.2** Add `storage/workspaces/{ws_id}/` helpers: `ensure_workspace(ws_id)`, `list_workspaces()`
- [ ] **8.1.3** On `POST /api/cloud/auth/register`, generate `ws_id=uuid4[:8]`, create `workspaces/{ws_id}/` with `datasets/`, `dashboards/`, `schedules/`, `reports/`, store `workspaces/{ws_id}/meta.json` (`name`, `owner_user_id`, `created_at`, `plan: free`), create user with `workspace_id`
- [ ] **8.1.4** JWT now includes `ws_id`; `get_current_user` sets `request.state.workspace_id`
- [ ] **8.1.5** Self-host fallback: if `CLOUD=false`, `workspace_id="default"` and `storage/workspaces/default/` is symlink to `storage/` (or just use `storage/` directly)
**Validation:** `pytest tests/test_workspace_isolation.py` (two workspaces, each sees only own datasets).

### Unit 8.2 — Billing (Stripe) (2 days)
**Surfaces:** `backend/app/api/cloud/billing.py` (new), `app/core/billing.py` (new), `app/config.py`, `storage/workspaces/{ws_id}/billing.json`
- [ ] **8.2.1** Add `stripe` to `requirements.txt` (`stripe==7.8`), `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO`, `TEAM`, `ENTERPRISE` in `.env.example`
- [ ] **8.2.2** `core/billing.py`: `get_plan(ws_id)`, `can_create_dataset(ws_id)` (checks `plan` vs `count`), `can_query(ws_id)` (checks monthly `queries` counter in `billing.json`), `increment_query(ws_id)`
- [ ] **8.2.3** `api/cloud/billing.py`: `POST /api/cloud/billing/checkout {plan}` → `stripe.checkout.Session.create(...)` → `{url}`, `POST /api/cloud/billing/webhook` (verify `Stripe-Signature`, handle `checkout.session.completed` → update `billing.json` to `plan`, `status=active`), `GET /api/cloud/billing` → `{plan, usage: {datasets, queries_this_month, rows}, quotas}`, `POST /api/cloud/billing/portal` → Stripe Customer Portal URL
- [ ] **8.2.4** Middleware: in `api/datasets.upload` + `api/chat`, if `free` and over quota → `402 Payment Required` with `{"detail": "Free limit 3 datasets, upgrade at /pricing"}`
- [ ] **8.2.5** Mock in tests: `stripe` calls patched, `webhook` tested with `stripe.Webhook.construct_event` mock
**Validation:** `pytest tests/test_billing_mock.py` (checkout mock, webhook, quota 402).

### Unit 8.3 — White-Label & Branding (0.5 day)
**Surfaces:** `backend/app/api/cloud/workspaces.py` (new), `frontend/streamlit_app.py`
- [ ] **8.3.1** `api/cloud/workspaces.py`: `GET/POST /api/cloud/workspaces/{ws_id}/brand` (admin/editor), `brand.json` (`app_name`, `logo_url`, `primary_color`)
- [ ] **8.3.2** Frontend: on load, `GET /api/cloud/workspaces/{ws_id}/brand` (if `CLOUD=true`) → `st.set_page_config(page_title=brand.app_name)` + `st.markdown(f"<style>:root {{--primary: {color}}")`
**Validation:** `pytest tests/test_brand.py`.

### Unit 8.4 — Local LLM (Ollama) (1 day)
**Surfaces:** `backend/app/agent/coder.py`, `explainer.py`, `app/api/cloud/llm.py` (new), `docker-compose.cloud.yml`
- [ ] **8.4.1** `api/cloud/llm.py`: `GET/POST /api/cloud/llm {provider, model, ollama_url, openai_key}` → `workspaces/{ws_id}/llm.json` (store `openai_key` encrypted via `Fernet` if `ENCRYPTION_KEY` set, else plain with warning)
- [ ] **8.4.2** `coder.py`/`explainer.py`: if `llm.provider=="ollama"` → call `httpx.post(f"{ollama_url}/api/generate", json={model, prompt})` instead of `openai`; if `openai` → use workspace's `openai_key` (BYOK) if present else global `OPENAI_API_KEY`
- [ ] **8.4.3** `docker-compose.cloud.yml` add `ollama: image: ollama/ollama:0.3` + `volumes: ollama:/root/.ollama` + `init` script `ollama pull llama3.1:8b`
**Validation:** `pytest tests/test_llm_ollama_mock.py` (mock ollama http).

### Unit 8.5 — Marketplace (0.5 day)
**Surfaces:** `backend/app/api/marketplace.py` (new), `storage/marketplace/`
- [ ] **8.5.1** Create `storage/marketplace/market_research.json`, `invoice_parser.json`, etc (10 files with `name`, `description`, `queries: ["..."]`, `dashboard_template: {widgets}`)
- [ ] **8.5.2** `api/marketplace.py`: `GET /api/marketplace?kind=`, `GET /api/marketplace/{id}`, `POST /api/marketplace/{id}/install` (copies queries as `dashboards` or `schedules` into `workspace`)
**Validation:** `pytest tests/test_marketplace.py`.

### Unit 8.6 — Admin & Landing (1.5 days)
**Surfaces:** `backend/app/api/cloud/admin.py` (new), `landing/` (new, Next.js or Vite)
- [ ] **8.6.1** `api/cloud/admin.py`: `GET /api/cloud/admin/stats` (admin only, if `user.role==admin` and `CLOUD=true`) → `{workspaces, active_subscriptions, mrr, total_datasets}`
- [ ] **8.6.2** `landing/`: `npm create vite` or `next create`, 3 pages `/` (hero + demo GIF + features), `/pricing` (cards $19/$49/$499), `/docs` (link to `README`), `Sign up` → `app.insightagent.com/auth?next=/`; `Caddyfile` for TLS
- [ ] **8.6.3** `landing/Dockerfile` + `docker-compose.cloud.yml` service `landing: build: ./landing ports: 3000:3000`
**Validation:** Manual `landing` opens, pricing shows 3 tiers.

### Unit 8.7 — Frontend: Cloud UI (1 day)
**Surfaces:** `frontend/streamlit_app.py`
- [ ] **8.7.1** If `CLOUD=true`, show `Workspace` switcher in sidebar (list `workspaces` user belongs to), `Billing` page (`GET /api/cloud/billing` → plan, usage, `Upgrade` button → Stripe Checkout), `Brand` page (logo/color), `LLM` page (provider select), `Marketplace` tab (list + Install)
- [ ] **8.7.2** If `402` from API (quota), show `st.error("Free limit reached, upgrade")` + `st.link_button("Upgrade", billing_url)`
**Validation:** Manual cloud flow: register → free quota 3 datasets → 4th upload → 402 → checkout mock → pro → upload again → 200.

### Unit 8.8 — Docs & Release (0.5 day)
- [ ] `CLOUD.md` (how to run `docker-compose.cloud.yml`, Stripe CLI `stripe listen`, Ollama `pull`), `README` add `insightagent.com` + self-host vs cloud table, tag `v1.0-cloud`, `v1.0` for self-host

**Total: ~8 days (3-4 weeks)**

## Validation Plan

| Check | Command | Expected |
|-------|---------|----------|
| All tests | `pytest tests -q` | 100+ passed |
| Workspaces | `pytest tests/test_workspace_isolation.py -v` | isolation |
| Billing | `pytest tests/test_billing_mock.py -v` | checkout mock, webhook, quota 402 |
| Brand | `pytest tests/test_brand.py -v` | get/post |
| LLM | `pytest tests/test_llm_ollama_mock.py -v` | ollama mock |
| Marketplace | `pytest tests/test_marketplace.py -v` | install |
| Landing | `npm run build` in `landing/` | 0 errors |
| Manual cloud | Register → 3 datasets ok → 4th 402 → Stripe mock → pro → 4th ok → brand → ollama | visual |
| Regression | `python /tmp/e2e_15_queries.py` + `docker-compose up` (self-host) | 15/15, no billing when `CLOUD=false` |

**Highest-risk:** Billing `402` blocks OSS. Mitigate: `CLOUD=false` bypasses all quota checks (tested as `if CLOUD and over_quota`).

## Risks / Rollback

| Risk | Mitigation | Rollback |
|------|------------|----------|
| `Stripe` webhook fails due to `STRIPE_WEBHOOK_SECRET` missing | In dev, `stripe listen` forwards; in CI mock; if webhook fails, log and return 200 so Stripe doesn't retry forever | Disable `CLOUD` → no billing |
| `workspace_id` in JWT leaks across tenants | `get_storage_path` uses `ContextVar`, test isolation | Revert to single `storage/` |
| `ollama` 10GB download fails on 2GB RAM | Make `ollama` profile `cloud` only, docs say `docker-compose --profile cloud up ollama` | Keep Ollama optional, fallback to OpenAI |
| `landing` Next.js adds `node_modules` 300MB | Keep `landing/` minimal (Vite, 50MB) or even `landing.html` static | Ship `landing/` as 1 HTML file |
| `billing.json` counter `queries_this_month` never resets | Add ` Cron` to reset monthly (APScheduler) or check `last_reset` date on read | Manual `rm billing.json` |

## Open Questions

- None. `Stripe`, `Ollama`, `Fernet`, `Vite` are MIT/Apache, proven. `CLOUD=false` keeps OSS buildable without any cloud env.

---

**Approval Gate:** Reply `Approve` to build Level 8, or `Change` to edit. This is the final level — after this you have **v1.0**.

---

## After L8: What You Have

- **Self-host OSS** (`docker-compose up`): full L1-L7, MIT, single workspace, no billing.
- **Cloud** (`docker-compose.cloud.yml`): multi-tenant, Stripe, white-label, Ollama, marketplace.
- Tag `v1.0` + `v1.0-cloud`, post to HN/Product Hunt, `mrr` starts.

**You finished. Pick Level 1 and start.**
