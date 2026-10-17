# 19: T-18: Agent Observation of Console Errors and Failed Network Requests

**What to build:** Capture `pageerror` unhandled exceptions, console errors, and failed network requests (status >= 400 or requestfailed) in the browser driver, bounded to a maximum length, wrapped in untrusted-content fences, and appended to action observations. Register `console_errors` as an explicit agent tool.

**Blocked by:** 10: T-09: Migrate Browser and API Agents to Shared Loop (Contract)

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Filtering on catalog.html captures the TypeError in tool observation output
- [ ] Console errors and network failures are delimited by untrusted-content fences
