# 04: T-04: Static Report HTML Escaping and Content Security Policy

**What to build:** Ensure every interpolated value in the HTML report generator (finding summaries, evidence content, step descriptions, IDs) is safely escaped using html.escape. Add a strict Content-Security-Policy meta tag to prevent script execution from reflected target content.

**Blocked by:** None (can start immediately)

**Status:** resolved

## Acceptance criteria

- [x] Evidence containing <script>alert(1)</script> renders as inert &lt;script&gt; in report.html
- [x] Report HTML document includes a strict Content-Security-Policy meta header
