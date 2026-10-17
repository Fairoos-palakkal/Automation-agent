# Verdict Pipeline: Engine Assertion, Fresh-Context Replay, and Finalization

## Status
Accepted (2026-10-17)

## Context
The core architectural premise of this project (ADR-0001) is that the LLM never decides a Verdict. However, the audit (F-02, F-19) revealed that `VerdictEngine.evaluate` was never called on the real run path, baseline findings used fingerprint-only steps that could not be replayed, and verdicts were stamped offline by the scoring CLI using substring keyword matching against solved challenges.

## Decision
1. **Finding Structure:** Agents must report structured findings (`where`, `expected`, `actual`, `selector_or_url`, `step_ids`). Evidence is automatically captured by the ToolGateway from actual tool observations (page DOM, network response, console logs), not model-supplied text.
2. **Execution Flow:**
   - On finding submission, `FindingVerifier` derives an `AssertionRule` from structured fields.
   - `VerdictEngine` executes deterministic assertions against live page state.
   - `Replayer` opens a fresh, isolated browser context and re-executes the recorded steps from `StepLog`.
   - `finalize_verdict(assertion_outcome, replay_outcome)` produces the final Verdict (`PASS`, `FAIL`, `INCONCLUSIVE`, `FLAKY`).
3. **Scoring Separation:** The Scoring Harness and CLI read existing verdicts; they never create, stamp, or modify verdicts.

## Consequences
- Every reported finding has an auditable, deterministic verdict reason and verifiable step history.
- Offline scoring evaluates recall and precision against ground truth without altering findings or run outcomes.
