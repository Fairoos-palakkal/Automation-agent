# 16: T-15: End-to-End Verdict Pipeline Verification on Own Site

**What to build:** Run an end-to-end execution against Own Site confirming planted DEFECT-004 through live engine evaluation and Challenger replay. Validate that verdict creation occurs exclusively within `verdict/` and `challenger` modules.

**Blocked by:** 15: T-14: FindingVerifier Integration into Task Completion Flow

**Status:** ready-for-agent

## Acceptance criteria

- [ ] E2E run on Own Site confirms DEFECT-004 with a deterministic FAIL verdict
- [ ] Grep audit verifies zero Verdict instantiation in scoring or CLI modules
