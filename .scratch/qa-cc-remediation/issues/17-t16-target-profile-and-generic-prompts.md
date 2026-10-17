# 17: T-16: TargetProfile Decoupling and Role-Generic Prompts

**What to build:** Strip all target-specific selectors, endpoints, payloads (e.g. `' or 1=1--`), and bug class hints from agent prompts. Implement `TargetProfile` as an auditable metadata container recorded in the trace. Baseline and multi-agent configurations use identical prompts and profiles.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## Acceptance criteria

- [ ] `grep -riE 'juice|noshery|rest/user|or 1=1|Me want' src/qa_cc/agents` returns zero matches
- [ ] TargetProfile contents are recorded in the `run_start` trace entry
