# 12: T-11: Structured Findings and Automatic Observation Evidence Capture

**What to build:** Update `report_finding` tool schema to accept structured fields: `{summary, expected, actual, selector_or_url, step_ids}`. The runtime automatically captures Evidence from the last real observation (DOM snapshot, console error, or HTTP exchange) and ignores model-fabricated evidence strings. Link step IDs to the shared StepLog.

**Blocked by:** 09: T-08: Shared AgentLoop and StepLog Architecture (Expand), 11: T-10: Run Identity, Directory Layout, and Validated TraceEntry Schema

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Findings in findings.json contain non-empty, non-fingerprint step lists referencing StepLog IDs
- [ ] Model-supplied `evidence_content` strings are ignored in favor of gateway-captured evidence
- [ ] Baseline findings are replayable with concrete actions and selectors
