# 07: T-07: Remove Verdict Stamping from Scorer and Label Unverified Findings

**What to build:** Excise all verdict creation and modification logic from `handle_score` and offline scoring scripts. Remove `--update-report`. Update report generation to label findings as "UNVERIFIED" unless stamped by a genuine VerdictEngine/Challenger execution.

**Blocked by:** None (can start immediately)

**Status:** resolved

## Acceptance criteria

- [x] grep -n "Verdict(" shows zero matches in src/qa_cc/scoring/ or CLI scoring handlers
- [x] Unverified findings without a code-evaluated verdict display an UNVERIFIED badge in report.html
