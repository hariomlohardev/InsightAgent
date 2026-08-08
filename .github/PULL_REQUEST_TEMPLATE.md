# Pull Request

## What
**Closes** #<id>
**Why** — problem + linked issue

## How
* Code path: `backend/app/...` / `sdk/...` / `docs/...`
* Tests: `backend/tests/test_*.py` added/updated?
* Bench: `scripts/bench_*.py` numbers if perf

## Checklist
- [ ] `make lint` 0 errors (`black` + `ruff` + `py_compile`)
- [ ] `make test` 155+ passed (or `pytest backend/tests/test_mything -v` for focused)
- [ ] `CONTRIBUTING.md` steps followed, `CODE_OF_CONDUCT.md` respected
- [ ] No `docker-compose up` break when `DATABASE_URL=""` and `REDIS_URL` empty (fallback)
- [ ] Docs updated if user-facing (`README`, `docs/`, `BENCHMARKS.md`)

## Screenshots (if UI)
