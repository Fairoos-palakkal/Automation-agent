# Published Results Must Be Generated from Scored Run Artifacts

## Status
Accepted (2026-10-17)

## Context
The audit (F-01) uncovered that `qa-cc results` printed a hard-coded dictionary of literals rather than aggregating measured runs. Furthermore, those literal values were published in `README.md` and `PROJECT_PORTFOLIO.md`, while the actual token consumption in live traces was an order of magnitude higher than claimed.

## Decision
1. **Remove Literals:** Hard-coded result dictionaries are completely excised from `cli.py` and across the codebase.
2. **Aggregated Results Only:** `qa-cc results` aggregates only valid `score.json` files from `runs/<config>/<run_id>/` directories. If no scored runs exist, it exits non-zero with "no scored runs found".
3. **Commit & Run Provenance:** All benchmark figures cited in documentation, portfolio materials, or reports must be directly produced by `qa-cc results` and must cite specific run IDs and the git commit hash.
4. **Honest Measurement Over Perfect Numbers:** A "no improvement" or higher-cost multi-agent outcome is accepted and documented as legitimate engineering findings; truth in benchmarking takes precedence over marketing claims.
5. **Held-out Set Integrity:** The held-out defect set is split from the tuning set, and only its SHA-256 hash is committed to the repository. Fresh un-leaked defects replace any tuning-contaminated items (e.g. DEFECT-007).

## Consequences
- Benchmark results are 100% reproducible by any external reviewer from committed run artifacts under `examples/` or locally executed runs.
- Empty or broken runs cannot produce misleading benchmark tables.
