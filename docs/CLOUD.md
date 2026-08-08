# Cloud Guide — Level 8

**InsightAgent Cloud** is open-core: OSS (`docker-compose up`) stays MIT single-workspace `default` with no billing. Cloud (`CLOUD=true`) adds multi-tenant workspaces, Stripe, white-label, Ollama, marketplace.

## Flags

| Flag | Default | Effect |
|------|---------|--------|
| `CLOUD` | `false` | When `true`, `get_storage_path()` → `storage/workspaces/{ws_id}/` + JWT carries `ws_id` |
| `STRIPE_SECRET_KEY` | `sk_test_mock` | `sk_test_...` real, `sk_test_mock` mocks checkout |
| `STRIPE_WEBHOOK_SECRET` | `whsec_mock` | Verify `Stripe-Signature` |
| `ENCRYPTION_KEY` | dev | Fernet key for BYOK `openai_key` (else plain) |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama service |

## Quick Start

```bash
# OSS — no billing, no CLOUD
cp .env.example .env   # CLOUD=false
docker-compose up
# Backend 8000, Frontend 8501, storage/ (single)

# Cloud — multi-tenant + Stripe mock
cp .env.example .env
# set CLOUD=true, STRIPE_SECRET_KEY=sk_test_mock
docker-compose -f docker-compose.cloud.yml up
# Backend 8000, Frontend 8501 (☁️ Cloud + 🛒 Market tabs), Landing 3000
# Or with real Stripe:
# STRIPE_SECRET_KEY=sk_test_... STRIPE_PRICE_PRO=price_... docker-compose -f docker-compose.cloud.yml up
```

Self-host without Stripe still boots: `if CLOUD=false` all quota checks are bypassed (`can_create_dataset` returns True). Tested as `test_no_cloud_regression`.

## Workspaces

- `POST /api/cloud/auth/register {email,pass,workspace_name}` → `{workspace_id, access_token (JWT with ws_id)}` → `storage/workspaces/{ws_id}/` with `datasets/`, `dashboards/`, `schedules/`, `billing.json` (`plan:free`), `meta.json`.
- JWT `ws_id` sets `ContextVar` via `get_current_user` → `get_storage_path()` isolates.
- `GET /api/datasets` only returns own workspace's datasets (validated in `test_workspace_isolation`).

## Billing

- `GET /api/cloud/billing` → `{plan, usage: {datasets, queries_this_month}, quotas}`
- `POST /api/cloud/billing/checkout {plan:pro|team|enterprise}` → Stripe Checkout `url` or mock `https://checkout.stripe.com/mock/...`
- `POST /api/cloud/billing/webhook` verifies `Stripe-Signature` (or mock JSON `{type:checkout.session.completed, data:{object:{client_reference_id:ws_id}}}`) → `billing.json` plan upgraded.
- `POST /api/cloud/billing/portal` → Stripe portal or mock.
- Quotas enforced in `POST /api/datasets/upload` and `POST /api/chat`: free `3 datasets, 50 queries/mo` → `402 Payment Required` (`test_billing_mock_checkout_webhook_quota`).
- Monthly `queries_this_month` resets when month changes (checked on `get_billing`).

In CI, Stripe is mocked: `STRIPE_SECRET_KEY=sk_test_mock` returns mock URL, webhook parses JSON directly.

## White-Label

- `GET/POST /api/cloud/workspaces/{ws_id}/brand {app_name,logo_url,primary_color}` — `enterprise` (and `team`) only, else `402`.
- Frontend: when `CLOUD=true` and logged in, `GET /api/cloud/workspaces/{ws_id}/brand` → `st.markdown(style)` injects `primary_color`, title shows `app_name`.
- `test_brand` covers free→402, enterprise→200.

## Local LLM

- `GET/POST /api/cloud/llm {provider,model,ollama_url,openai_key}` → `workspaces/{ws_id}/llm.json` (BYOK encrypted with `ENCRYPTION_KEY` via `Fernet` if set, else plain).
- `POST /api/cloud/llm/test` → hits `ollama_url/api/tags` or mock.
- `docker-compose.cloud.yml` service `ollama: ollama/ollama:0.3` with `volumes: ollama:/root/.ollama`, profile `cloud` (optional, 10GB). Test mocks httpx.
- `test_llm_ollama_mock` verifies BYOK and ollama provider.

## Marketplace

- `storage/marketplace/*.json` seeded with 10 templates (`market_research`, `invoice_parser`, etc) via `_ensure_marketplace_seed()`; each has `{queries, dashboard_template}`.
- `GET /api/marketplace` → list, `GET /api/marketplace/{id}` → detail, `POST /api/marketplace/{id}/install {dataset_id}` → clones dashboard + 3 widgets into workspace.
- `test_marketplace` installs `Market Research` into new workspace.

## Admin

- `GET /api/cloud/admin/stats` (`admin` only) → `{total_workspaces, mrr, active_subscriptions, total_datasets, active_schedules}` — `mrr` sums `pro 19 + team 49 + enterprise 499`.
- `test_admin_stats` checks admin 200, viewer 403.

## Landing

- `landing/` is Vite + static `index.html` (hero, features, pricing `$0/$19/$49/$499`, docs). `npm run build` → `dist/` (validated in CI). `docker-compose.cloud.yml` service `landing: build ./landing → 3000:3000`.
- Static 50KB, no `node_modules` bloat in repo (only `package.json`).

## Self-host vs Cloud

|  | Self-host (`docker-compose up`) | Cloud (`docker-compose.cloud.yml`) |
|---|---|---|
| Workspaces | `default` single | `storage/workspaces/{ws_id}/` per tenant |
| Billing | none | Stripe mock/real, quotas 402 |
| Branding | none | `brand.json` per ws |
| LLM | env `OPENAI_API_KEY` | per-ws `llm.json` BYOK/Ollama |
| Landing | none | `landing` on 3000 |

See `plans/08_LEVEL_08_CLOUD.md` for full spec.
