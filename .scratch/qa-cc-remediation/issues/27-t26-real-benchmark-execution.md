# 27: T-26: Benchmark Execution: 3 Baseline, 3 Multi-Agent, 1 Held-Out Run

**What to build:** Execute the full benchmark suite: 3 baseline runs and 3 multi-agent runs on the tuning set, 1 final run on the held-out set, and Juice Shop benchmark across D4 Objectives. Commit curated run artifacts under `examples/` and generate the README and PORTFOLIO benchmark table directly via `qa-cc results` citing run IDs and commit hash.

**Blocked by:** 16: T-15: E2E Verdict Pipeline Verification on Own Site, 18: T-17: Orchestrator Run-Level Budget Enforcement, Replan, and Shared Findings, 19: T-18: Agent Observation of Console Errors and Failed Network Requests, 20: T-19: History Context Pruning, Interactive Element Index, and Budgets, 21: T-20: Per-Agent Caller Permissions and Gateway-Controlled Screenshots, 22: T-21: Randomized Fence Delimiters and Adversarial Injection Verification, 23: T-22: Multi-Turn Loop Detector and Recovery Behavior, 24: T-23: Scoring Harness Rewrite for PRD §9 Metrics and D4 Scoreboard Delta, 25: T-24: Playwright Crawler and Coverage Metric Integration, 26: T-25: Held-Out Defect Re-Seal and Cryptographic Hash Lock

**Status:** ready-for-agent

## Acceptance criteria

- [ ] `qa-cc results` generates the published markdown table from real `score.json` files
- [ ] Mean and spread are reported across the 3 baseline and 3 multi-agent runs
- [ ] Published numbers cite verified run IDs and git commit hash
