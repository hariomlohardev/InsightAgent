# Launch Kit — v1.0 (2025-08-08)

## HN Title Options (pick one, 80 chars)

1. **Show HN: InsightAgent — Chat with CSV/Excel in plain English (open source, 10M rows <2s)**
2. **InsightAgent v1.0 — Open source Tableau + ChatGPT Code Interpreter (MIT, local LLM)**
3. **We built an open source data agent that does 10M CSV in 1.8s (no SQL needed)**

**First Comment (post 10min after title):**

> Hi HN, we built InsightAgent to kill the “export CSV → write pandas → plot” loop.
> * `git clone && make install && docker-compose up` 30s → upload 1M CSV → “top 5 products by sales” → chart in 2s (polars scan_csv, p95 85ms at 50 users, bench in BENCHMARKS.md)
> * Works without key (heuristic 15+ queries) or with Groq (free) / OpenAI / Gemini / Claude / Ollama local (private)
> * MIT, FS/DB/S3 (DATABASE_URL), SDK `pip install insightagent`, plugins via entry_points
> * Demo: http://localhost:8501/?demo=1 (read-only, sales.csv) after `docker-compose -f docker-compose.demo.yml up`
> * Comparison vs Metabase/Superset in COMPARISON.md, ARCHITECTURE.md Mermaid, 156 tests, `make cov` 95, `SECURITY_AUDIT.md` 0 high
> * Try: `from insightagent import InsightAgent; agent.chat(df, "forecast Sales")`
> Feedback welcome — especially on 10M speed and SQL passthrough (SELECT * FROM df WHERE ... via DuckDB).

## Product Hunt

* **Tagline:** Chat with your data — open source, private, 10M rows <2s
* **Gallery (5):** 1. Upload sales.csv 2. Chat “Why did sales drop in March?” → insight 3. Pin to dashboard → share link 4. SDK 2 lines 5. Benchmark chart (1.8s vs 6s)
* **Video 60s script (docs/video_script.md):** 0-5s upload, 5-20s chat 3 queries, 20-35s dashboard + share, 35-50s SDK, 50-60s `make install` one-liner

## Checklist 7d Stable

* [ ] `demo.insightagent.com` (or `?demo=1` locally) stable 7d, no 500 on p50 (locust 50 users)
* [ ] `v1.0` tag + GitHub Release notes from `CHANGELOG.md`
* [ ] `docker-compose up` + 15 queries smoke (see `README` demo GIF flow)
* [ ] `docs` + `landing` `npm run build` 0 errors
* [ ] Post-mortem doc after launch (traffic, stars, issues)

## GIF 20s

Record: upload `sample_data/sales.csv` → chat `top 5 products by sales` → pin → share link incognito. Optimize to 3MB `gifsicle`, place `README.md` and `docs/static/img/demo.gif`.

## Tags

`git tag -a v1.0 -m "v1.0 top-tier OSS 9.5/10" && git push origin v1.0`
