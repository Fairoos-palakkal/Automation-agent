# Verdicts are deterministic; there is no runtime evaluation agent

Real testing is black-box, so an LLM judge would have no ground truth either, and its PASS/FAIL calls would bring back the hallucination problem this system exists to avoid. Verdicts come only from the Verdict Engine and deterministic replay; scoring against Planted Defects happens offline in the Scoring Harness. The Challenger agent may dispute a Finding and downgrade it to INCONCLUSIVE, but can never upgrade a Finding or set a Verdict.

**Considered options:** an LLM evaluation agent at runtime (rejected: non-reproducible verdicts); manual-only scoring (rejected: not repeatable across Runs and prone to generous grading, kept only for triaging Findings that match no Planted Defect).
