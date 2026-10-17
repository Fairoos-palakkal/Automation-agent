# 11: T-10: Run Identity, Directory Layout, and Validated TraceEntry Schema

**What to build:** Implement strict run isolation with `run_id` and filesystem layout `runs/<config>/<run_id>/`. Implement a validated Pydantic `TraceEntry` schema that records served `model_id` and token counts on every model call, records denied tool calls, traces in `finally` blocks, and chains sequence numbers.

**Blocked by:** 09: T-08: Shared AgentLoop and StepLog Architecture (Expand)

**Status:** ready-for-agent

## Acceptance criteria

- [ ] All trace entries conform to the Pydantic TraceEntry schema
- [ ] Every model call trace entry includes the served model_id and token usage
- [ ] Denied tool calls (e.g. allowlist violations) produce trace entries in trace.jsonl
- [ ] Token counts aggregated from trace.jsonl match the final RunResult totals
