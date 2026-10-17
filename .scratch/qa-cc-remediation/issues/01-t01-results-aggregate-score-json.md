# 01: T-01: Aggregate Real score.json Files and Remove Hard-Coded Literals

**What to build:** Make `qa-cc results` read and aggregate `runs/<config>/<run_id>/score.json` files and exit non-zero with "no scored runs found" when no runs exist. Delete all hard-coded dictionary literals from `cli.py`. Clean README and PORTFOLIO of all fabricated figures and unverified claims (cryptographic trace, automatic scrubbing, 100% replay, 0 hallucinations). Results output prints mean and spread across runs.

**Blocked by:** None (can start immediately)

**Status:** resolved

## Acceptance criteria

- [x] Running `qa-cc results` in an empty directory exits with status code 1 and prints "no scored runs found"
- [x] Modifying or adding a fixture `score.json` changes the aggregated results table
- [x] README.md and PROJECT_PORTFOLIO.md contain zero fabricated tables or claims not backed by code
- [x] Documentation cites LLM_API_KEY instead of BAI_API_KEY
