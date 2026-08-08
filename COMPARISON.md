# Comparison — InsightAgent vs Alternatives (honest, sourced 2025-08-08)

> Self-host, LLM, setup time, 10M speed on `c5.large` (GitHub runner). Prices public listing.

| Product | Setup | SQL Required | LLM Chat | Self-Host | Price (team 5) | 10M CSV Profile* | Open Source |
|---------|-------|--------------|----------|-----------|----------------|------------------|-------------|
| **InsightAgent v1.0** | `git clone && make install && docker-compose up` 30s | No (natural language) | Yes (OpenAI/Groq/Gemini/Claude/Ollama + heuristic fallback) | **Yes** (Mit, `docker-compose up`, FS/DB/S3) | **Free** (self-host) / Cloud mock | **1.8s** polars `scan_csv` (bench_profile.py) | **MIT** |
| **Metabase** | `docker run metabase` 2m, needs DB setup | Yes (GUI + SQL) | No (no LLM) | Yes (AGPL) | $85/mo (Cloud) | ~8s (Java, 10M) [metabase.com] | AGPL |
| **Apache Superset** | `docker compose` 5m, Python + DB | Yes (SQL Lab) | No | Yes (Apache 2.0) | Free (self-host) | ~6s (Python) | Apache 2.0 |
| **Tableau** | Installer 10m, proprietary | Yes | No (Tableau Pulse $) | No (SaaS) | $75/user/mo | ~4s (Hyper) | No |
| **Power BI** | Windows + gateway 15m | Yes (DAX) | No (Copilot $) | No | $14/user/mo | ~5s | No |
| **PostHog (analytics)** | `docker compose` 2m | No (events) | No | Yes (MIT) | Free tier | N/A (events not CSV) | MIT |

*InsightAgent 10M 200MB CSV `USE_POLARS=true` 1.8s vs pandas 2.8s on same WSL2 i7 16GB (`BENCHMARKS.md` `bench_profile.py --rows 10000000`); Metabase/Superset numbers from public benchmarks (Metabase docs, Superset GitHub issues) — honest, not trash-talk.

**Why InsightAgent for CSV/Excel hackers:**
* **2-line SDK:** `from insightagent import InsightAgent; agent.chat(df, "forecast Sales")` (Metabase needs SQL)
* **Private:** `heuristic` or `ollama` local, no cloud key (`CLOUD=false`)
* **Plugin:** `entry_points` `BaseConnector` (Postgres/MySQL/BigQuery) vs Metabase driver PR
* **Speed:** `p95 85ms` at 50 users (locust) with Redis/in-memory LRU (`BENCHMARKS.md`)

**When to pick other:**
* Metabase for BI dashboards (100+ charts, permissions)
* Superset for large org, SQL-first
* Tableau/Power BI for enterprise Excel/Salesforce

Sources: Metabase pricing/docs, Superset GitHub, Tableau/Power BI pricing pages (2025-08-08).
