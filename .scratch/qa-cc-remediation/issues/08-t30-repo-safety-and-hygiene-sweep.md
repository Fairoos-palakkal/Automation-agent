# 08: T-30: Repository Safety Sweep, .gitignore, and Baseline Verification

**What to build:** Audit git history and .env handling for committed credentials; add comprehensive .gitignore ignoring .env, .venv, egg-info, __pycache__, .DS_Store, and stray run directories. Execute Own Site and multi-agent e2e tests on a machine with Playwright browsers installed to establish a verified baseline.

**Blocked by:** None (can start immediately)

**Status:** resolved

## Acceptance criteria

- [x] Git history scan shows zero committed API keys or credentials
- [x] .gitignore is in place covering build artifacts, virtualenvs, local caches, and secrets
- [x] The two e2e tests that could not run in the audit sandbox are executed and recorded
