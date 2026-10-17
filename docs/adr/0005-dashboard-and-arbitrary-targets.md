# Live Dashboard and User-Specified Target Execution (Scope Amendment)

## Status
Accepted (2026-10-17)

## Context
PRD §2 originally listed a live dashboard and arbitrary-target testing as non-goals to focus on the core CLI engine and avoid SSRF / off-target prompt injection risks. However, live visual monitoring and user-specified target exploration ("paste-any-site") provide significant portfolio demonstration value when paired with robust safety controls.

## Decision
1. **Scope Inclusion:** Amend the PRD to include a live web dashboard and user-specified target exploration in the product roadmap.
2. **Explicit Allowlist Guard:** User-specified targets require explicit user confirmation and are dynamically registered in the runtime allowlist for that Run only. Arbitrary unconfirmed URLs remain strictly prohibited.
3. **SSRF and Off-Target Prevention:** Playwright request interception (`context.route`) and HTTP redirect checking strictly enforce that child requests, navigation clicks, and redirects cannot escape the registered target host.
4. **Live Dashboard Streaming:** The dashboard monitors `runs/<config>/<run_id>/` and live trace streams without modifying agent execution state or interfering with deterministic assertions.

## Consequences
- Demonstrations can show real-time agent execution across arbitrary web apps while preserving strict security boundaries.
- Safety invariants (exact-host allowlist, untrusted content delimiters, credential scrubbing) remain non-negotiable.
