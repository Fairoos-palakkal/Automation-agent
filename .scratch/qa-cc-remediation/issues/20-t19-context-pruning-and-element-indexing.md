# 20: T-19: History Context Pruning, Interactive Element Index, and Budgets

**What to build:** Implement context pruning that retains full content only for the newest observation while compacting older turns into one-line summaries. Replace massive raw HTML snapshots with an interactive element index (role, name, selector, state) capped at 2–4K characters. Enforce max model calls and wall-clock time budgets.

**Blocked by:** 09: T-08: Shared AgentLoop and StepLog Architecture (Expand)

**Status:** ready-for-agent

## Acceptance criteria

- [ ] A 25-turn run shows approximately linear prompt token growth instead of quadratic bloat
- [ ] Multi-agent Own Site run token consumption fits within the planned token reserve
