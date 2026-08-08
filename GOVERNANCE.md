# Governance

## Roles
* **Maintainers** — review, merge, release, `CODEOWNERS` (`@insightagent/maintainers`)
* **Committers** — triage issues, label PRs
* **Contributors** — anyone with a merged PR (listed in `CONTRIBUTORS.md` future)

## Decision Making
* Rough consensus + lazy approval: PR with 1 maintainer approval + 24h no objection → merge
* Major changes (DB, auth, docs host) → issue + 2 maintainer approvals
* Releases: `vX.Y.Z` semantic, `CHANGELOG.md` updated, tag triggers CI

## Communication
* Issues: bugs/features via templates
* Security: `security@insightagent.local` (private, see `SECURITY.md`)
* Conduct: `conduct@insightagent.local` (see `CODE_OF_CONDUCT.md`)

## License
MIT — see `LICENSE`. Frictionless OSS: `CLOUD=false` single tenant, `DATABASE_URL`/`S3` optional.
