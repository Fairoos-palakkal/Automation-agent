# 24: T-23: Scoring Harness Rewrite for PRD §9 Metrics and D4 Scoreboard Delta

**What to build:** Relocate scoring harness to `src/qa_cc/scoring/`. Evaluate recall via structured matchers against frozen defects, compute triaged precision, replay rate, unsupported findings, coverage, and token cost into `score.json`. Score OWASP Juice Shop as a before/after scoreboard difference restricted to D4 Objectives (Authentication, Basket/Checkout, Search/Input Handling). Refuse mixed-model comparisons using trace model IDs.

**Blocked by:** 11: T-10: Run Identity, Directory Layout, and Validated TraceEntry Schema, 12: T-11: Structured Findings and Automatic Observation Evidence Capture, 15: T-14: FindingVerifier Integration into Task Completion Flow

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Golden fixture runs generate deterministic `score.json` files with all PRD §9 metrics
- [ ] Juice Shop scoring measures the delta between pre-run and post-run scoreboards restricted to D4
- [ ] Unreachable Juice Shop scoreboard raises an explicit error rather than silently returning 0.0 recall
- [ ] Comparing runs with differing served model IDs is refused
