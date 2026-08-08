# Backup & Restore — InsightAgent L09

> Postgres + filesystem + S3 all need backups. This doc covers the 30s recovery a contributor can run.

## Postgres (when DATABASE_URL set)

**Automated `pg_dump` cron (prod):**

```bash
# daily 02:00 UTC, keep 7 days
# set in docker-compose prod or K8s CronJob
0 2 * * * pg_dump "$DATABASE_URL" | gzip > /backups/insightagent-$(date +\%F).sql.gz && \
  find /backups -mtime +7 -delete

# restore
gunzip -c /backups/insightagent-2025-08-08.sql.gz | psql "$DATABASE_URL"
# or via Alembic
# alembic upgrade head  # re-creates tables, then restore data above
```

Health check `GET /health` returns `{"db":{"status":"connected","latency_ms":12}}` — if `filesystem` it means `DATABASE_URL` not set (expected for contributors).

**No DB?** No backup needed — filesystem `storage/` is source of truth. DB is optional; filesystem remains.

## Filesystem (default `CLOUD=false`)

```
storage/
  datasets/{id}/data.csv + meta.json + versions/{v}.csv
  workspaces/{ws_id}/... # when CLOUD=true
  conversations/{id}.json
```

**Backup tar:**

```bash
tar -czf /backups/fs-$(date +%F).tar.gz storage/
# per-workspace tar (when CLOUD=true)
for ws in storage/workspaces/*; do
  tar -czf /backups/ws-$(basename $ws)-$(date +%F).tar.gz "$ws"
done
```

**Restore:**

```bash
tar -xzf /backups/fs-2025-08-08.tar.gz -C ./
# verify
ls storage/datasets | wc -l
```

## S3 (`STORAGE_BACKEND=s3` + `S3_BUCKET`)

Datasets are dual-written to `s3://$S3_BUCKET/datasets/{id}/data.csv` + `meta.json` via `fsspec/s3fs`. S3 itself is durable, but enable:

* **Versioning** on bucket (`aws s3api put-bucket-versioning --bucket $S3_BUCKET --versioning-configuration Status=Enabled`)
* **Lifecycle** 30d to IA, 90d to Glacier (optional)
* **Cross-region replication** for prod

**Manual S3 backup (when not using versioning):**

```bash
aws s3 sync s3://$S3_BUCKET/datasets ./s3-backup/datasets --endpoint-url $S3_ENDPOINT
# restore
aws s3 sync ./s3-backup/datasets s3://$S3_BUCKET/datasets --endpoint-url $S3_ENDPOINT
```

Tests use `moto` mock — no real AWS needed: `pytest tests/test_storage_s3_mock.py -v`.

## Checklist before release

- [ ] `pg_dump` cron runs and `ls /backups/*.sql.gz` shows yesterday
- [ ] `tar -tzf /backups/fs-*.tar.gz` lists `datasets/`
- [ ] `GET /health` shows `db.connected` when `DATABASE_URL` set, `filesystem` otherwise
- [ ] `docker compose --profile db config` shows `postgres:16-alpine`
