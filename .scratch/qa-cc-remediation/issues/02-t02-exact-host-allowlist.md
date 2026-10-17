# 02: T-02: Exact-Host URL Allowlist Enforcer

**What to build:** Implement a shared exact-host URL validation function using urllib.parse.urlsplit that enforces http/https schemes, rejects userinfo, and performs exact hostname or host:port matching against the configured allowlist. Shared by ToolGateway and Crawler.

**Blocked by:** None (can start immediately)

**Status:** resolved

## Acceptance criteria

- [x] TargetNotAllowed is raised for bypass attempts: localhost.evil.com, evil.com/?next=localhost, localhost@evil.com
- [x] TargetNotAllowed is raised for scheme variations, IPv6 anomalies, userinfo, trailing dots, and port mismatches
- [x] ToolGateway and Crawler share the exact same validation logic
