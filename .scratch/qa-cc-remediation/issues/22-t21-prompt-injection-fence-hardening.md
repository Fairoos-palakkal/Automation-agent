# 22: T-21: Randomized Fence Delimiters and Adversarial Injection Verification

**What to build:** Generate per-run random fence token names, strip fence delimiter tokens from untrusted content, add explicit system prompt instructions treating fenced content as inert data, and wrap HTTP bodies and console output. Write a non-tautological injection test feeding feedback.html.

**Blocked by:** 03: T-03: HTTP Redirect Manual Inspection and Playwright Request Interception

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Page content attempting to close the delimiter (e.g. `</UNTRUSTED_DOM_CONTENT>`) cannot escape the fence
- [ ] Injection test fails if the ToolGateway allowlist check is removed
