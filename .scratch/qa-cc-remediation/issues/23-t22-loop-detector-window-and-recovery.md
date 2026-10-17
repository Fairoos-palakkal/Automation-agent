# 23: T-22: Multi-Turn Loop Detector and Recovery Behavior

**What to build:** Implement sliding-window loop detection capable of catching alternating patterns (ABAB, ABCABC) using post-action observation fingerprints. Implement progressive recovery (fresh snapshot with warning message, forced alternate tool/selector, terminating with `loop_terminated`). Harden Planner JSON parsing and typed budget validation.

**Blocked by:** 09: T-08: Shared AgentLoop and StepLog Architecture (Expand)

**Status:** ready-for-agent

## Acceptance criteria

- [ ] ABAB and ABCABC action sequences trigger loop recovery and eventual `loop_terminated` status
- [ ] Planner validates 1-6 tasks, enforces unique IDs, handles fenced JSON, and ensures sum of task budgets <= total budget
