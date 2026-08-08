# Cloud — How to run `docker-compose.cloud.yml`, Stripe CLI, Ollama

See `docs/CLOUD.md` for full guide.

```bash
# OSS
docker-compose up
# Cloud (mock Stripe, no real charge)
CLOUD=true docker-compose -f docker-compose.cloud.yml up
# Cloud with real Stripe (test mode)
# 1. stripe listen --forward-to localhost:8000/api/cloud/billing/webhook
# 2. STRIPE_SECRET_KEY=sk_test_... STRIPE_PRICE_PRO=price_... docker-compose -f docker-compose.cloud.yml up
# 3. POST /api/cloud/billing/checkout → Stripe URL → pay with 4242 4242 4242 4242 → webhook upgrades plan
# Ollama (optional, local LLM, 100% private)
docker-compose -f docker-compose.cloud.yml --profile cloud up ollama
docker exec ollama ollama pull llama3.1:8b
# set per-workspace LLM to ollama via UI ☁️ Cloud → LLM → ollama
```
