# 25: T-24: Playwright Crawler and Coverage Metric Integration

**What to build:** Build an SPA-aware Crawler on Playwright that traverses target links and forms within the exact-host allowlist to output `inventory.json`. Integrate `score` calculation of Coverage by comparing run steps against the inventory.

**Blocked by:** 02: T-02: Exact-Host URL Allowlist Enforcer, 24: T-23: Scoring Harness Rewrite for PRD §9 Metrics and D4 Scoreboard Delta

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Crawler produces an inventory listing all pages, forms, and interactive routes on Own Site
- [ ] `score.json` includes a valid `coverage` metric computed from executed steps vs inventory
