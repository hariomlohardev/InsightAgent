branchProtection:
  # Apply via GitHub UI once: Settings → Branches → Add rule for `main`
  # Required status checks (must match job names in ci.yml -> gate):
  requiredChecks:
    - gate
  requiredReviews: 1
  dismissStaleReviews: true
  requireCodeOwnerReviews: false
  requireConversationResolution: true
  enforceAdmins: false
  allowForcePushes: false
  allowDeletions: false
  # Contributor flow:
  flow: |
    1. Contributor forks → PR (any branch → main)
    2. CI runs automatically: lint, backend (3.10/3.11/3.12 + integration), bench 100k (<1s), frontend AppTest empty-profile, docker config, security (soft)
    3. Welcome bot comments on first PR with exact local commands (make format / make test)
    4. Auto-label by path (backend/frontend/perf/docker/docs) + auto-assign reviewer (hariomlohardev)
    5. Maintainer sees single ✅ `gate` check (all required jobs) → one review → Merge → auto-merge not enabled, manual merge keeps control
    6. Dependabot weekly PRs labeled `deps` → same gate, one review
    7. CodeQL weekly + dep-review on PRs for security
  localCheck: |
    make lint && make test
    # same as CI gate, run before push:
    # - black --check, ruff, mypy (soft), py_compile
    # - pytest -q (filesystem fallback, no DB/Redis needed)
    # - bench: PYTHONPATH=backend python scripts/bench_profile.py --rows 100000 --json --per-col
    # - frontend: python -m py_compile frontend/streamlit_app.py + AppTest
