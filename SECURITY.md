# Security Policy

## Supported Versions
| Version | Supported |
|---------|-----------|
| `main`  | ✅ |
| `<0.9`  | ❌ |

## Reporting a Vulnerability
Do **not** open a public issue. Email `security@insightagent.local` with:
* description + impact
* steps to reproduce (PoC CSV/query if needed)
* suggested fix if any

We will acknowledge within 48h, triage within 5 days, and disclose via `SECURITY.md` + release notes after fix.

## Hardening
* `app/core/storage.py` sanitizes filenames (`../` blocked, 120 char limit, `[^a-zA-Z0-9._-]` → `_`)
* `app/core/security.py` sandboxes `exec` via `get_safe_globals` (no `import` in generated code, `duckdb` for SQL)
* `app/api/datasets.py` enforces `ALLOWED_EXT` + `MAX_UPLOAD_MB` + streaming 8KB chunks
* `JWT` + `RBAC` (`viewer/editor/admin`) when `AUTH_REQUIRED=true`
* `S3` via `fsspec`/`boto3` with env creds, never logged

## Disclosure
We follow coordinated disclosure: fix → test → tag → advisory.
