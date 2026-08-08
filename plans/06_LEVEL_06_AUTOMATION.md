# Level 6 — Automation & Collaboration: Reports That Run Themselves (OSS)

> **From one-off analysis to daily insights your team actually sees.**

---

## Goal

Automate **reports, alerts, and team sharing** so insights don't die in chat. After Level 6, you can schedule *"Email PDF of Sales by Region every Monday 9am + Slack alert if Sales drops >10% day-over-day"* and your team gets it, with comments on the report.

## Success Criteria

- [ ] **Scheduled Reports:** `POST /api/schedules {dashboard_id|query, cron: "0 9 * * 1", channel: "email|slack", to: "..."}` → `storage/schedules/{id}.json` + `APScheduler` or `Celery Beat` runs at cron, re-executes stored `code` on current data, generates `PDF`/`PNG`/`CSV`, sends via `SMTP`/`Slack webhook`; manual `POST .../run` for testing; `GET /api/schedules` lists; `DELETE` cancels
- [ ] **Alert:** `threshold` schedule: `if result["Sales"].sum() < last_sum*0.9` then send `Slack` + `Email` ("Sales dropped 12% vs yesterday")
- [ ] **Slack/Discord Bot:** `/insight top products` in Slack → calls `POST /api/chat` via bot token + returns `result` + `chart_url` (upload PNG to Slack)
- [ ] **Comments:** On dashboard/report, `POST /api/dashboards/{id}/comments {text}` → threaded comments stored in `dashboards/{id}.json` (`comments: [{user, text, at}]`), `GET` lists, `DELETE`
- [ ] **Report Builder:** In Dashboard Studio, `Build Report` → pick widgets + add `markdown` blocks + `title` → `POST /api/reports {dashboard_id, blocks}` → `storage/reports/{id}.json` → `GET /api/reports/{id}/export?format=pdf` → PDF with cover + widgets + tables (via `reportlab` or `weasyprint`)
- [ ] **Exports:** Any `result` can be `Download CSV` (already), plus `Export PDF` of dashboard (L3 stretch now done via `reportlab` without `kaleido`), `Export PNG` of chart (if `kaleido` present)
- [ ] `pytest` 80+ tests (add 10), `py_compile` clean, no regression; `docker-compose` adds `redis` + `beat` if Celery, or `APScheduler` in-process for OSS simplicity
- [ ] README adds Automation GIF + Slack demo, `docs` maybe

## Context & Current Facts

**L5 delivered:**
- Deep analytics (why, outliers, forecast), 70+ tests, filesystem versioning, dashboards, connectors.

**Pain:** Insights are pull, not push. Manager doesn't open app to check dashboard. Need push: "Dashboard PDF in email every Monday" + "Slack #sales gets top products daily" + "Comment on chart: 'Check Region West'".

## Constraints & Non-Goals

**Constraints:**
- Stay MIT, keep filesystem + Streamlit, keep `docker-compose up` <3 min (add `redis` only if needed, else `APScheduler` in-process)
- No external SaaS for scheduling besides user-provided `SMTP`/`Slack webhook` (no SendGrid lock-in)
- No new DB — keep filesystem (`storage/schedules`, `storage/reports`, `dashboards` comments)

**Non-Goals (for L6):**
- No SMS/WhatsApp (defer to post-L8)
- No real-time collab cursors (comments are enough)
- No Airflow (too heavy; `APScheduler` is enough for <100 schedules)

## Key Decisions

| Decision | Recommended | Why |
|----------|-------------|-----|
| **Scheduler** | `APScheduler` (in-process, `BackgroundScheduler`) with `CronTrigger` for OSS; store jobs in `storage/schedules/{id}.json` + memory; on boot, reload from files and add jobs. Alt `Celery+Redis` is more robust but adds 2 services; keep APScheduler for L6 OSS, Celery is L7 enterprise if needed | Alt: `Celery Beat` needs Redis + worker, heavier; APScheduler is 100KB, no extra container, fine for <100 jobs |
| **PDF** | `reportlab` (pure Python, 1MB) to generate PDF: cover + each widget `result` as table + `chart` as PNG (via `plotly.io.write_image` with `kaleido` if available else placeholder "Chart: see dashboard link") | Alt: `weasyprint` needs `pango` system dep, heavier; `reportlab` is simplest for text+table, chart image is optional |
| **Slack bot** | OSS: user provides `SLACK_BOT_TOKEN` + `SLACK_SIGNING_SECRET`, we expose `POST /api/slack/events` (verify signature, handle `app_mention` + `slash` `/insight`) → calls `chat_service` → replies via `chat.postMessage` with text+image | Alt: Socket Mode needs extra lib; webhook mode is simpler, docs show ngrok for local |
| **Comments** | Inline in `dashboards/{id}.json` as `comments: [{id, user: "anon"|"email", text, created_at, parent_id}]` (flat thread), max 100 per dashboard | Alt: separate `comments/` adds scan; inline is fine for <1k comments |
| **Report Builder** | New `storage/reports/{id}.json` with `blocks: [{type: "widget"|"markdown", widget_id|text}]` + `dashboard_id` linkage; export reuses dashboard's `result`/`chart` | Alt: full Notion blocks overkill; 2 types cover 95% (chart+text) |
| **Frontend** | Streamlit: new `⏰ Schedules` tab in sidebar (list, create form with cron builder `0 9 * * 1` + channel), `💬 Comments` expander under each dashboard widget, `📄 Report Builder` page | Alt: separate app adds nav; tabs keep single-page |

## Recommended Approach

Add **three services**: `scheduler` (APScheduler), `exporter` (PDF), `slack` (events), plus **storage** for `schedules`/`reports`/`comments`.

Reuse `executor` for scheduled re-execution, `dashboard_service` for widget fetching.

### Data Flow

```
Schedule: UI → POST /api/schedules {dashboard_id, cron, channel} → storage/schedules/{id}.json + scheduler.add_job(cron, func=run_schedule)
         run_schedule → load dashboard → for each widget.code → executor on current df → new result/chart → generate PDF via exporter → send via email/slack
Slack: Slack → POST /api/slack/events (verify) → chat_service → reply
Comments: POST /api/dashboards/{id}/comments → append to dashboards/{id}.json
Report: Dashboard Studio → Build Report → POST /api/reports → export PDF
```

## Work Plan (Ordered)

### Unit 6.1 — Scheduler Storage & Service (1.5 days)
**Surfaces:** `backend/app/core/storage.py` (schedules), `app/services/scheduler_service.py` (new), `requirements.txt` (`APScheduler==3.10.4`, `reportlab==4.1.0`)
- [ ] **6.1.1** Add `storage/schedules/{id}.json`: `{id, dashboard_id|query, dataset_id, cron, channel, to, threshold?, created_at, last_run, next_run, enabled}`
- [ ] **6.1.2** `scheduler_service.create_schedule(data)`, `list_schedules`, `delete_schedule`, `run_schedule_now(id)` (manual trigger for testing), `run_schedule(id)` (cron job body)
- [ ] **6.1.3** On `app/main.py` startup (`@app.on_event("startup")`), `scheduler = BackgroundScheduler(); for s in list_schedules(): scheduler.add_job(run_schedule, CronTrigger.from_crontab(s.cron), args=[s.id], id=s.id)`
- [ ] **6.1.4** `run_schedule` does: `load_dashboard_or_query` → `executor` per widget/query → `exporter` PDF → `sender` (email/slack)
**Validation:** `pytest tests/test_scheduler_storage.py` + `TestClient` create/list/run-now/delete.

### Unit 6.2 — Exporter (PDF/CSV) (1 day)
**Surfaces:** `backend/app/core/exporter.py` (new)
- [ ] **6.2.1** `exporter.dashboard_to_pdf(dashboard, results)` → `reportlab` platypus: title, date, each widget: `Paragraph(title)`, `Table(result.data)`, `Image(chart_png if kaleido else Spacer)`; return `BytesIO`
- [ ] **6.2.2** If `kaleido` not installed, `plotly.io.write_image` fails gracefully, PDF still has tables + "View chart at {share_url}"
- [ ] **6.2.3** `GET /api/reports/{id}/export?format=pdf|csv|json` (new report API, but also `GET /api/dashboards/{id}/export?format=pdf` for dashboard)
**Validation:** `pytest tests/test_exporter.py` (create dashboard with 2 widgets → export PDF → bytes >1k).

### Unit 6.3 — Email & Slack Senders (1 day)
**Surfaces:** `backend/app/core/senders.py` (new)
- [ ] **6.3.1** `send_email(to, subject, body, attachments)` via `smtplib.SMTP` with `SMTP_HOST/PORT/USER/PASS` from `.env` (user provides Gmail app password or local `mailpit` for dev)
- [ ] **6.3.2** `send_slack(webhook_url, text, file=None)` via `requests.post(webhook_url, json={text})`; if `file` (PNG), use `files.upload` if bot token, else just text + link
- [ ] **6.3.3** Add `.env.example` `SMTP_HOST=, SMTP_PORT=587, SLACK_WEBHOOK_URL=`
**Validation:** `pytest tests/test_senders_mock.py` (mock SMTP/webhook, assert called).

### Unit 6.4 — Slack Bot (1.5 days)
**Surfaces:** `backend/app/api/slack.py` (new), `app/main.py`
- [ ] **6.4.1** `POST /api/slack/events` → verify `X-Slack-Signature` + `X-Slack-Request-Timestamp` (5min window) using `SLACK_SIGNING_SECRET`, handle `url_verification` (return `challenge`), `app_mention`/`message` → extract text after `<@bot>`, call `chat_service.process_query_v2(dataset_id from default or `datasets?` lookup, query=text)` → `chat.postMessage` to `channel` with `insight` + `result` table text + `chart` as uploaded image if possible
- [ ] **6.4.2** Slash `/insight` → similar, but `command` payload
- [ ] **6.4.3** Docs: `docs/slack.md` with ngrok + create app steps
**Validation:** `pytest tests/test_slack_events.py` (mock request with valid signature, 200).

### Unit 6.5 — Comments & Reports (1 day)
**Surfaces:** `backend/app/api/dashboards.py` (extend), `app/api/reports.py` (new), `core/storage.py`
- [ ] **6.5.1** `POST /api/dashboards/{id}/comments {text, parent_id?}`, `GET .../comments`, `DELETE .../comments/{cid}` → stored inline in `dashboards/{id}.json`
- [ ] **6.5.2** `POST /api/reports {dashboard_id, blocks, name}`, `GET /api/reports`, `GET /api/reports/{id}`, `GET /api/reports/{id}/export?format=pdf`
- [ ] **6.5.3** `storage/reports/{id}.json` handling
**Validation:** `pytest tests/test_comments.py tests/test_reports.py`.

### Unit 6.6 — API: Schedules (1 day)
**Surfaces:** `backend/app/api/schedules.py` (new), `app/main.py`
- [ ] **6.6.1** `POST /api/schedules`, `GET /api/schedules`, `GET /api/schedules/{id}`, `DELETE /api/schedules/{id}`, `POST /api/schedules/{id}/run` (manual), `GET /api/schedules/{id}/runs` (last 5 runs with status)
**Validation:** `pytest tests/test_api_schedules.py`.

### Unit 6.7 — Frontend: Schedules, Comments, Report Builder (1.5 days)
**Surfaces:** `frontend/streamlit_app.py`
- [ ] **6.7.1** New sidebar `⏰ Schedules`: list (cron, next run, last status), form `Dashboard` select + `Cron` (text `0 9 * * 1` + helper "Daily 9am") + `Channel` (Email/Slack) + `To` + `Create`; `Run Now` + `Delete` per row
- [ ] **6.7.2** Under each dashboard widget card, `💬 Comments` expander: `st.text_input` + `Post` + list
- [ ] **6.7.3** In Dashboard Studio, `📄 Build Report` → `st.text_area(markdown)` + widget checkboxes + `Save Report` + `Export PDF`
- [ ] **6.7.4** Show `Last run` status in Studio if dashboard has schedule
**Validation:** Manual: create dashboard → schedule daily email (mock) → Run Now → see "Sent" → check `storage/schedules` → Slack webhook test → comment → report PDF.

### Unit 6.8 — Docs & Release (0.5 day)
- [ ] Tag `v0.6-automation`, GIF, release notes

**Total: ~9 days (2-3 weeks)**

## Validation Plan

| Check | Command | Expected |
|-------|---------|----------|
| All tests | `pytest tests -q` | 80+ passed |
| Scheduler | `pytest tests/test_scheduler_storage.py tests/test_api_schedules.py -v` | create/run-now/delete |
| Exporter | `pytest tests/test_exporter.py -v` | PDF bytes >1k even without kaleido |
| Senders | `pytest tests/test_senders_mock.py -v` | mock SMTP/webhook called |
| Slack | `pytest tests/test_slack_events.py -v` | 200 with valid sig, 401 without |
| Comments | `pytest tests/test_comments.py -v` | post/get/delete |
| Reports | `pytest tests/test_reports.py -v` | create + export |
| Manual | Schedule + Run Now → email/slack mock → comment → report PDF | all visual |
| Regression | `python /tmp/e2e_15_queries.py` + analytics + connectors | still green |

**Highest-risk:** Scheduler in-process dies on restart. Mitigate by persisting jobs to files and reloading on startup (already), and `Run Now` for testing without waiting for cron.

## Risks / Rollback

| Risk | Mitigation | Rollback |
|------|------------|----------|
| `APScheduler` jobs lost on crash | Persist `schedules/*.json`, reload on `startup`; add `last_run` log | Revert to no scheduler, keep manual `run` |
| `reportlab` PDF without chart images looks sparse | Include table + "View chart" link, note in docs | Keep PDF as tables-only, add `kaleido` later |
| `Slack` signature verification fails due to time skew | Allow 5min window, log raw body for debug | Disable verification behind `SLACK_VERIFY=false` for dev |
| Email SMTP blocked by sandbox (no outbound) | Mock in tests, docs say "use Mailpit locally" | Keep email as optional, Slack webhook is enough for OSS demo |

## Open Questions

- None. `APScheduler` + `reportlab` are MIT, proven, no new DB.

---

**Approval Gate:** Reply `Approve` to build Level 6, or `Change` to edit.
