# 03: T-03: HTTP Redirect Manual Inspection and Playwright Request Interception

**What to build:** Configure HttpTool to disable automatic redirects and manually follow redirects up to 5 hops, re-validating every intermediate hop against the exact-host allowlist. Enforce response body size cap (256 KB). In PlaywrightDriver, install context.route interception to abort any request to non-allowlisted hosts.

**Blocked by:** 02: T-02: Exact-Host URL Allowlist Enforcer

**Status:** resolved

## Acceptance criteria

- [x] 302 redirect from an allowed host to a disallowed host raises TargetNotAllowed
- [x] HTTP response bodies exceeding 256 KB are capped or rejected
- [x] External link clicks or background network requests in browser sessions are aborted and traced as denials
