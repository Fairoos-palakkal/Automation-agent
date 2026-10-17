# 18: T-17: Orchestrator Run-Level Budget Enforcement, Replan, and Shared Findings

**What to build:** Ensure Orchestrator charges every TaskResult to a global `RunState` and halts execution when global action or token limits are reached. Handle `failed` and `loop_terminated` task statuses, trigger replanning up to at most 2 times (refusing and tracing the 3rd), inject `prior_findings` into sub-agent prompts, and isolate each task in a fresh browser context.

**Blocked by:** 10: T-09: Migrate Browser and API Agents to Shared Loop (Contract)

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Global `--max-actions` stops multi-agent execution even when sub-agent budgets remain
- [ ] A task failure triggers replanning; the third failure is refused and traced
- [ ] Completed task IDs are not re-executed during replan
- [ ] Summaries of prior findings appear in subsequent sub-agent prompts as already reported
