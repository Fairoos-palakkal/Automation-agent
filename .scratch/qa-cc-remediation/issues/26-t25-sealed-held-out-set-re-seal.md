# 26: T-25: Held-Out Defect Re-Seal and Cryptographic Hash Lock

**What to build:** Replace contaminated DEFECT-007 with fresh held-out defects. Separate `defects.tuning.json` from the sealed held-out file, committing only its SHA-256 hash. Enforce a one-time `--final` scoring execution that writes a timestamped lock file and prevents subsequent held-out runs. Widen ground-truth lexical isolation test to all of `src/qa_cc/`.

**Blocked by:** 24: T-23: Scoring Harness Rewrite for PRD §9 Metrics and D4 Scoreboard Delta

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Running `qa-cc score --final` twice is refused by lock file enforcement
- [ ] Ground-truth isolation test covers all source modules except scoring
- [ ] Only the SHA-256 hash of the held-out defect file is committed to git
