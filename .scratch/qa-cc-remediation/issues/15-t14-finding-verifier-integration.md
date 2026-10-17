# 15: T-14: FindingVerifier Integration into Task Completion Flow

**What to build:** Implement `FindingVerifier` to derive an `AssertionRule` from structured finding fields, run VerdictEngine assertions on live state, trigger Challenger replay, call `finalize_verdict`, write the resulting verdict and reason to findings.json and trace.jsonl, and render verdict badges and step lists on report cards.

**Blocked by:** 13: T-12: VerdictEngine Real CSS Selectors, Status-Code Rules, and FLAKY Retry, 14: T-13: Replayer in Fresh Browser Context and Challenger Integration

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Integration test with FakeProvider on a local fixture page sets finding verdict from VerdictEngine
- [ ] A finding whose assertion passes on replay is stamped INCONCLUSIVE with a recorded reason
- [ ] The generated HTML report displays verdict reasons, step lists, and trace links
