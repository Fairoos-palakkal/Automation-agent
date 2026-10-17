# 05: T-05: Runtime Secret and Token Scrubbing on the Live Path

**What to build:** Activate a central Scrubber on the live execution path. Ensure LLM_API_KEY from environment, Bearer tokens, JWT-shaped patterns (ey...), Authorization headers, and Set-Cookie values are scrubbed from JSONL traces, findings.json, and HTML reports.

**Blocked by:** None (can start immediately)

**Status:** resolved

## Acceptance criteria

- [x] Mock or live run with test API keys and JWT response payloads yields zero secret matches when grepping the run output directory
- [x] TraceWriter, ToolGateway, Finding serialization, and ReportGenerator use the shared Scrubber
