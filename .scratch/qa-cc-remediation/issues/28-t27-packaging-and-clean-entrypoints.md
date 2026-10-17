# 28: T-27: Packaging, Dependencies, and Clean Command Entry Points

**What to build:** Clean up packaging configuration in `pyproject.toml`, organize optional extras (e.g. `fastapi`, `uvicorn`), remove duplicate documentation files and stray run output folders, and ensure `pip install .` enables `qa-cc run`, `score`, and `results` to run from any working directory.

**Blocked by:** 27: T-26: Benchmark Execution: 3 Baseline, 3 Multi-Agent, 1 Held-Out Run

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Installing the package into a fresh environment allows `qa-cc run` from any directory
- [ ] Clean git checkout contains no generated run artifacts or stray PNGs
