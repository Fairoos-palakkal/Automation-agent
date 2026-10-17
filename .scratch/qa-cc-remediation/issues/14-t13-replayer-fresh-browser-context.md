# 14: T-13: Replayer in Fresh Browser Context and Challenger Integration

**What to build:** Build a `Replayer` that launches a clean, fresh browser context and re-executes the recorded steps from StepLog. Wire the Challenger agent to request replay on reported findings and downgrade non-reproducible findings to INCONCLUSIVE (never upgrade).

**Blocked by:** 12: T-11: Structured Findings and Automatic Observation Evidence Capture

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Replaying steps for a planted defect in a fresh browser context reproduces the defect
- [ ] Non-reproducible or non-deterministic findings are downgraded to INCONCLUSIVE
- [ ] Replay outcomes and Challenger determinations are recorded in trace.jsonl
