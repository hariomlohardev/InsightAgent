# BF Matrix — Before vs Blazing vs Competitors

> **Source of truth:** `BENCHMARKS.md:5-35` before, `BENCHMARKS.json` after (per-level commit hash), `COMPARISON.md:5-13` competitor numbers sourced 2025-08-08.

## 1. Before → Blazing (same WSL2 i7 16GB, no GPU, 10M × 5 200MB CSV)

| # | Metric (how measured) | Before L10 | After BF-06 (target) | Delta | Level that moves it | Evidence file |
|---|-----------------------|------------|----------------------|-------|---------------------|----------------|
| M1 | Profile 10M `USE_POLARS=true` (`bench_profile --rows 10000000`) | **1.80s** | **0.85s** | **-53%** 950ms | BF-02 (vectorize) + BF-04 (single read) | `BENCHMARKS.json:profile_ms` |
| M2 | Profile 10M `USE_POLARS=false` (pandas chunked) | **2.80s** | **1.70s** | -39% 1.1s | BF-02 | same |
| M3 | Profile 1M polars | **0.80s** | **0.38s** | -53% | BF-02 | same |
| M4 | Chat groupby 1M | **45ms** (32ms DuckDB) | **24ms** (18ms DuckDB) | -47% | BF-02 + BF-03 cache | `bench_chat.py` |
| M5 | Chat repeat (cache HIT) | **85ms** (no HIT) | **<5ms** | -94% | BF-03 | `X-Cache: HIT` |
| M6 | Dashboard widget 100k | **8ms** | **4ms** | -50% | BF-02 | `bench_chat.py:widget` |
| M7 | GET HIT `X-Cache` | **6ms** | **4ms** | -33% | BF-03 (adds preview/chat) | `curl -i` + `test_cache_hit_lt_10ms` |
| M8 | GET `?q=` 200 datasets | **90ms** | **18ms** (DB trigram) / 60ms FS | -80%/ -33% | BF-04 | `EXPLAIN ANALYZE` |
| M9 | Upload 100MB | **3.2s** + double read | **1.9s** single pass | -41% | BF-04 | `time curl -F` |
| M10 | Locust 50u p95 | **85ms** Redis / 120ms FS | **55ms** / 90ms | -35%/ -25% | BF-03 + BF-06 | `locust --csv` |
| M11 | Locust 100u p95 | **~180ms** (extrapolated) | **<130ms** | -28% | BF-06 | same 100u run |
| M12 | Frontend preview payload | **120KB** (20 cols) | **32KB** | -73% | BF-05 | `wc -c` |
| M13 | Frontend TTI | **400ms** | **170ms** | -57% | BF-05 | AppTest `time` |

**Overall “blazing” claim:** `10M <0.9s` (was 1.8s) is **2.1×** faster, still **9×** faster than Metabase 8s.

### Per-level waterfall (so we know which PR gave what)

| Level | M1 10M polars after | Cumulative saving vs 1.80s |
|-------|---------------------|---------------------------|
| L10 before | 1.80s | 0 |
| BF-01 measure | 1.80s | 0 (no code) |
| BF-02 hot path | **1.05s** | -0.75s (-42%) |
| BF-03 cache | 1.02s (profile same, chat 5ms) | -0.78s |
| BF-04 storage single-pass + parquet | **0.90s** | -0.90s |
| BF-05 frontend (no backend) | 0.88s | -0.92s |
| BF-06 scale (no single-profile) | 0.85s | -0.95s |

BF-02 alone is 79% of the win — if we stop after BF-02, we already claim “1.0s blazing”.

## 2. InsightAgent vs Competitors — Honest, Sourced (updates `COMPARISON.md`)

| Product | Setup | SQL Required | LLM Chat | Self-Host | Price team 5 | 10M Profile* | After BF | Open Source |
|---------|-------|--------------|----------|-----------|--------------|--------------|----------|-------------|
| **InsightAgent BF** | `clone && make install && docker-compose up` 30s | No | Yes (5 providers + heuristic) | Yes MIT FS/DB/S3 | Free / Cloud mock | **0.85s** | — | **MIT** |
| InsightAgent L10 | same | same | same | same | same | **1.80s** | — | MIT |
| Metabase | `docker run` 2m + DB | Yes GUI+SQL | No | Yes AGPL | $85/mo Cloud | ~8s | ~8s | AGPL |
| Superset | `docker compose` 5m Python+DB | Yes SQL Lab | No | Yes Apache2 | Free | ~6s | ~6s | Apache2 |
| Tableau | Installer 10m | Yes | Pulse $ | No SaaS | $75/user/mo | ~4s Hyper | ~4s | No |
| Power BI | Windows gateway 15m | Yes DAX | Copilot $ | No | $14/user/mo | ~5s | ~5s | No |

*InsightAgent 10M `bench_profile.py --rows 10000000` on WSL2 i7 16GB; others from public docs/issues per `COMPARISON.md:14`. BF 0.85s is **9.4×** Metabase, **7×** Superset, **4.7×** Tableau on same class CSV (not Hyper).

**Why still choose other:** Metabase for 100+ chart BI, Superset for SQL org, Tableau/Power BI for Salesforce. InsightAgent wins for CSV/Excel hackers who want `sum Sales by Region` without SQL and <1s.

## 3. Option Matrix — What we chose and what we didn’t (so PR reviewer sees trade)

| Area | A (chosen) | B (rejected) | C (rejected) | Why A |
|------|------------|--------------|--------------|-------|
| Read | Polars scan streaming | Pandas chunks only | DuckDB read_csv | A 2.1×, B fallback keeps compat |
| Profile | Vectorized once + approx >1M | Per-col loop + ThreadPool | Sample 100k extrapolate | A -0.46s, B still GIL, C loses accuracy |
| Cache | LRU+Redis+chat+preview+SWR | Redis required | No chat cache | A <10ms without Redis |
| Storage | Single-pass + parquet | Double read | COPY to Postgres | A -0.22s, no new infra |
| Frontend | Trim+page+cache_data | Next.js rewrite | Gzip only | A -73% payload, no rewrite |
| Search | ilike FS + pg_trgm GIN | Meilisearch | No index | A 18ms, no service |

## 4. Risk-adjusted matrix (what if assumption breaks)

| If | Then M1 becomes | Still blazing? |
|----|-----------------|----------------|
| Polars streaming not in 1.10 | 1.05s → 1.15s (fallback collect) | Yes (<1.8s) |
| Parquet skipped (no pyarrow) | 0.90s → 0.95s | Yes |
| Redis absent (FS only) | p95 55ms → 90ms | Yes (<150ms) |
| DB not Postgres (sqlite) | `?q=` 18ms → 60ms | Yes |
| 10M × 20 cols (800MB) on 2GB | 0.85s → 1.4s (spills) | Still <1.8s, but not 0.85s — document |

## 5. Level-vs-Metric heatmap (which level to cut if short on time)

|  | M1 10M | M5 chat cache | M9 upload | M12 payload |
|---|--------|---------------|-----------|-------------|
| BF-02 | ██████ | ░ | ░ | ░ |
| BF-03 | ░ | ██████ | ░ | ░ |
| BF-04 | ███ | ░ | ██████ | ░ |
| BF-05 | ░ | ░ | ░ | ██████ |

If 3d only: do BF-02 + BF-03 → get 1.05s + 5ms chat (80% perceived speed).

## 6. How to read the matrix in CI

- Each cell links to a commit hash of `BENCHMARKS.json` (e.g., `bf02-a1b2c3: {"profile_ms": 1050}`).
- `scripts/bench_locust_parse.py --p95 150 --csv /tmp/locust_stats.csv` exits 1 if p95 breaches, so CI fails fast.
- Competitor row is not tested — it’s sourced docs, update yearly or mark stale.

## 7. Non-goals not in matrix (so we don’t overclaim)

- LLM latency (Groq 200ms) not in M1 — profile is local, chat 5ms is without LLM (LLM adds 200ms but cached).
- Network RTT not in M7 — HIT 4ms is server time, browser adds ~20ms.
