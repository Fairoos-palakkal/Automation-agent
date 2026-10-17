# 13: T-12: VerdictEngine Real CSS Selectors, Status-Code Rules, and FLAKY Retry

**What to build:** Enhance VerdictEngine with real CSS selector semantics (classes, attributes, hierarchies via BeautifulSoup/Playwright), status-code assertions, URL normalization (trailing slash tolerance), robust text matching inside nested markup, and bounded assertion retries producing FLAKY and PASS_AFTER_RETRY verdicts. Ensure console error checks ignore benign messages.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## Acceptance criteria

- [ ] `element_exists` with `.buy` or `button.buy` returns PASS when present and FAIL when absent
- [ ] Trailing slash differences in URLs do not cause false assertion failures
- [ ] Inconsistent retry outcomes are labeled FLAKY rather than silently marked PASS
