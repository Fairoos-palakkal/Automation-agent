# 30: T-29: Live Web Dashboard and User-Specified Target Execution (ADR-0005)

**What to build:** Build a real-time web dashboard displaying live agent execution steps, captured evidence, and verified findings. Implement user-specified target mode ("paste-any-site") requiring explicit allowlist registration and user confirmation, while strictly preserving exact-host routing and SSRF protection (ADR-0005).

**Blocked by:** 27: T-26: Benchmark Execution: 3 Baseline, 3 Multi-Agent, 1 Held-Out Run

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Web dashboard streams real-time step log, evidence snapshots, and finalized verdicts
- [ ] User-specified targets require explicit confirmation and cannot navigate off-target
