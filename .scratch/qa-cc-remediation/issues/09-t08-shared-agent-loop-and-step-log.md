# 09: T-08: Shared AgentLoop and StepLog Architecture (Expand)

**What to build:** Build a shared `AgentLoop` and `StepLog` component alongside existing agent loops. Migrate `BaselineAgent` to use `AgentLoop`. Replace silent exception swallowing with structured error statuses (`llm_error`, `tool_error`, `invalid_args`) that are recorded in the trace and update RunState. Reject malformed tool-arg JSON instead of executing with {}.

**Blocked by:** 01: T-01: Aggregate Real score.json Files and Remove Hard-Coded Literals, 02: T-02: Exact-Host URL Allowlist Enforcer, 04: T-04: Static Report HTML Escaping and Content Security Policy, 05: T-05: Runtime Secret and Token Scrubbing on the Live Path, 06: T-06: Fail-Fast Initialization and Provider Error Handling, 07: T-07: Remove Verdict Stamping from Scorer and Label Unverified Findings, 08: T-30: Repository Safety Sweep, .gitignore, and Baseline Verification

**Status:** resolved

## Acceptance criteria

- [x] Existing baseline tests remain green when run on AgentLoop
- [x] LLM failure produces `llm_error` run status and creates a trace error event
- [x] Malformed tool arguments are rejected with an error rather than passing empty dicts
