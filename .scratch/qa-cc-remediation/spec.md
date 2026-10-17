# Spec: Agentic QA Command Center Remediation (Phases 5–10)

**Feature Slug:** `qa-cc-remediation`  
**Status:** `ready-for-agent`  
**Date:** 2026-10-17  
**Traceability:** Remediation of Implementation Audit (F-01 through F-24) mapped against PRD Revision 2026-10-14 and ADRs 0001–0005.

---

## Problem Statement

While the project has clean seams, type annotations, and 114 passing unit tests, an in-depth audit revealed that its run path does not deliver its core promises:
1. **Credibility & Measurement:** The benchmark table printed by `qa-cc results` and published in the README and portfolio contains hard-coded string literals rather than measured data (F-01). Committed multi-agent traces consumed ~981K tokens per run versus 18K–37K claimed.
2. **Missing Verdict Pipeline:** `VerdictEngine.evaluate` is never invoked during a run; findings produce `verdict=None` or have `FAIL` stamped post-hoc by the offline scoring script using keyword substring matches (F-02, F-03, F-19).
3. **Pervasive Security Gaps:** The target allowlist relies on a naive substring check that is bypassed by lookalike domains (`localhost.evil.com`) and HTTP redirects; secret scrubbing is never enabled on the live run path; prompt-injection fences can be prematurely terminated by page content; and the HTML report renders evidence as unescaped raw HTML (F-04, F-05, F-08, F-09, F-10).
4. **Target Leakage in Prompts:** Prompts explicitly mention Juice Shop selectors, SQLi payloads, and Noshery defect names, invalidating claims of black-box evaluation (F-07).
5. **Brittle Control Flow & Context Bloat:** The agent loop is duplicated three times; the orchestrator never charges run-level budgets; replanning is unreachable; console errors cannot be observed; and history is never pruned, causing quadratic prompt growth reaching 46K tokens by turn 40 (F-11, F-12, F-13, F-21, F-22).
6. **Ground Truth Contamination:** Planted defect DEFECT-007 was implemented in the test mock API during Phase 2 tuning, breaking held-out blindness (F-23).

---

## Solution

Implement Phases 5 through 10 of the remediation plan via strict test-driven development:
- **Phase 5 (Stop the Bleeding):** Remove hard-coded literals; make `qa-cc results` aggregate `runs/<config>/<run_id>/score.json` files and exit non-zero when empty; enforce an exact-host allowlist and redirect limits; escape all report HTML; activate runtime secret scrubbing; fail fast on missing keys or browsers; and establish repository hygiene.
- **Phase 6 (One Loop, Real Evidence):** Unify Baseline, Browser, and API agent loops into a single `AgentLoop`; record all actions into a structured `StepLog`; generate verifiable run directories with attributable `TraceEntry` records; and report structured findings backed by captured evidence.
- **Phase 7 (Verdicts from Code):** Wire `FindingVerifier` into task completion; execute `VerdictEngine` assertions on live state; perform fresh-context replays using `Replayer`; and derive final verdicts (`PASS`, `FAIL`, `INCONCLUSIVE`, `FLAKY`) solely through code.
- **Phase 8 (Agents That Really Work):** Decouple prompt instructions from target knowledge using `TargetProfile`; charge orchestrator actions and tokens to a global `RunState`; handle `failed` and `loop_terminated` statuses; prune conversation context and send compact interactive element indices; surface bounded console errors; and harden prompt injection defenses.
- **Phase 9 (Measure Honestly):** Rewrite the scoring harness to evaluate PRD §9 metrics from structured findings and scoreboard differences for D4 Objectives (Authentication, Basket/Checkout, Search/Input Handling); re-seal held-out defects with fresh un-leaked items and a hash lock; and conduct real benchmark runs.
- **Phase 10 (Ship & Stretch):** Clean packaging and CLI entry points; serve mock backend for API testing; and implement the live dashboard and user-specified target mode with strict allowlist confirmation (ADR-0005).

---

## User Stories

1. As a CLI operator, I want `qa-cc results` to aggregate only real `score.json` files across run directories, so that I never see fabricated benchmark metrics.
2. As a CLI operator, I want `qa-cc results` to exit with an error code and "no scored runs found" when no runs exist, so that empty directories do not falsely appear scored.
3. As a security engineer, I want the ToolGateway to enforce an exact-host allowlist using parsed hostname comparisons, so that lookalike domains like `localhost.evil.com` or `evil.com/?next=localhost` are blocked.
4. As a security engineer, I want the HTTP tool to follow redirects manually up to 5 hops and re-validate every hop against the allowlist, so that target redirect chains cannot escape the allowed perimeter.
5. As a security engineer, I want Playwright requests to be intercepted and blocked if they attempt to request external origins, so that off-target link clicks and subresources are thwarted.
6. As a security engineer, I want environment secrets (like `LLM_API_KEY`), Authorization headers, session cookies, and JWT-shaped strings to be automatically scrubbed from traces, findings, and reports, so that sensitive tokens never leak to disk.
7. As a security engineer, I want the HTML report to escape all user and target-controlled strings and enforce a Content Security Policy, so that reflected DOM content cannot trigger XSS.
8. As a developer, I want the CLI to fail immediately with an informative message if `LLM_API_KEY` is missing or Playwright fails to initialize, so that broken runs do not silently proceed.
9. As a developer, I want all three agents (Baseline, Browser, API) to run on a single unified `AgentLoop`, so that bug fixes and budget checks are universally consistent.
10. As a developer, I want every tool execution to be recorded in a chronological `StepLog` with distinct step IDs, so that findings can reference verifiable historical actions.
11. As an auditor, I want every run to be stored in an isolated `runs/<config>/<run_id>/` directory with an auditable `trace.jsonl`, so that all tool and model calls are attributable.
12. As an auditor, I want every `TraceEntry` to record the served model ID and token count, so that mixed-model runs are detected and rejected.
13. As an agent, I want `report_finding` to accept structured fields (`where`, `expected`, `actual`, `selector_or_url`, `step_ids`), so that findings do not rely on subjective, model-typed evidence.
14. As the runtime, I want Evidence objects to be automatically populated from real tool observation artifacts (DOM snapshot, screenshot, console logs, HTTP exchange), so that hallucinations are prevented.
15. As the QA engine, I want `FindingVerifier` to convert structured findings into `AssertionRule` checks and execute them through `VerdictEngine` on live DOM state, so that verdicts are deterministic.
16. As the Challenger agent, I want `Replayer` to spin up a fresh, clean browser context and re-execute finding steps from the `StepLog`, so that defect reproducibility is verified.
17. As the QA engine, I want `finalize_verdict` to combine live assertions and replay outcomes, so that flakiness or non-reproducibility is accurately labeled `FLAKY` or `INCONCLUSIVE`.
18. As a developer, I want the Scoring Harness to strictly read finalized verdicts and never create or overwrite verdicts, so that ADR-0001 is respected.
19. As a benchmarking engineer, I want agent prompts to contain zero target-specific strings, selectors, or SQL injection payloads, so that runs test agent intelligence rather than prompt authoring.
20. As a benchmarking engineer, I want target-specific metadata to be supplied exclusively via an auditable `TargetProfile`, so that baseline and multi-agent runs can be evaluated with and without target hints.
21. As an orchestrator, I want task execution to charge a global `RunState` and terminate once global action or token limits are reached, so that multi-agent runs respect budget bounds.
22. As an orchestrator, I want sub-agents to receive summaries of `prior_findings`, so that subsequent tasks do not duplicate reported defects.
23. As an orchestrator, I want replanning to be triggered when a task returns `failed` or `loop_terminated`, up to a strict limit of 2 replans, with the third refusal logged in the trace.
24. As a Browser Agent, I want bounded console error logs and failed HTTP requests (status >= 400) to be appended to action feedback, so that unhandled JavaScript errors and 500s are detectable.
25. As a runtime, I want previous conversation turns to be summarized and interactive elements indexed into a compact representation, so that prompt context grows linearly rather than quadratically.
26. As a security engineer, I want prompt-injection defense to utilize randomized run-specific delimiters and prompt system instructions, so that target pages cannot close fences.
27. As a benchmarking engineer, I want the scoring harness to evaluate recall, precision, replay rate, coverage, and cost against ground truth, so that all PRD §9 metrics are recorded in `score.json`.
28. As a benchmarking engineer, I want OWASP Juice Shop to be evaluated as a before-and-after scoreboard delta restricted to D4 Objectives (Authentication, Basket/Checkout, Search/Input Handling), so that pre-existing challenge solves do not skew results.
29. As a researcher, I want the held-out defect set to be split from the tuning set with only its SHA-256 hash committed in git, so that blind evaluation integrity is guaranteed.
30. As a developer, I want to view a real-time web dashboard displaying live agent steps and verified findings with strict allowlist guards (ADR-0005), so that stakeholder demonstrations are engaging and secure.

---

## Implementation Decisions

### Architectural Seams & Modules
- **`AgentLoop` (`src/qa_cc/agents/loop.py`):** Unifies tool calling, JSON parsing, loop detection, budget decrements, error handling, and `report_finding` invocation into a single component. `BaselineAgent`, `BrowserAgent`, and `ApiAgent` become configuration profiles over `AgentLoop`.
- **`StepLog` (`src/qa_cc/agents/step_log.py`):** Maintains sequential records of `{step_id, tool, args, url_before, status, error, evidence_id}`.
- **`FindingVerifier` (`src/qa_cc/verdict/verifier.py`):** Derives `AssertionRule` from structured findings, runs `VerdictEngine`, calls `Replayer`, and invokes `finalize_verdict`.
- **`Replayer` (`src/qa_cc/agents/replayer.py`):** Creates an isolated browser session, replays recorded steps from `StepLog`, and evaluates the assertion rule.
- **`ToolGateway` (`src/qa_cc/gateway/gateway.py`):**
  - Uses `urllib.parse.urlsplit` to enforce exact hostname / port equality without userinfo.
  - Intercepts Playwright routes (`context.route`) to abort non-allowlisted network requests.
  - Limits HTTP redirects to 5 hops, checking each intermediate hop.
  - Enforces caller permissions (`allowed_callers` per tool).
  - Enforces deterministic, unique screenshot file paths (`artifacts/<run_id>/<step_id>.png`).
- **`Scrubber` (`src/qa_cc/trace/scrubber.py`):** Central scrubber masking `LLM_API_KEY`, Bearer tokens, JWT patterns (`ey[A-Za-z0-9_-]+\...`), and Set-Cookie / Authorization headers.
- **`TargetProfile` (`src/qa_cc/agents/profile.py`):** Structured container for target entrypoints and hints, referenced in `run_start` trace entries.
- **`ScoringHarness` (`src/qa_cc/scoring/harness.py`):** Moved into `src/qa_cc/scoring/`, evaluating PRD §9 metrics from structured matchers and Juice Shop scoreboard deltas for D4 Objectives.
- **`LiveDashboard` (`src/qa_cc/dashboard/`):** Lightweight web dashboard streaming live trace logs and findings under ADR-0005.

---

## Testing Decisions

- **Test-Driven Development:** Every ticket begins with a failing test (red), followed by minimal code to pass (green), followed by refactoring.
- **Unit Suite Invariants:** Fast and completely deterministic. Network access, live browser instances, and real LLMs are strictly forbidden. `FakeProvider` and recorded cassettes are used exclusively.
- **Isolated Integration & E2E:** Real browser tests and live LLM contract tests are marked `@pytest.mark.e2e` and `@pytest.mark.live` and excluded from standard pytest execution.
- **Parametrized Security Tests:** Exhaustive test cases covering URL bypasses (`localhost.evil.com`, `evil.com/?next=localhost`, IPv6, userinfo, trailing dot, port mismatch) and prompt injection breakouts.
- **Golden File Verification:** Test fixtures for `score.json`, `trace.jsonl`, and `findings.json` to ensure scoring calculations are deterministic.

---

## Out of Scope

- Multi-tenant authentication, RBAC, and hosted cloud deployments.
- CI/CD automation pipelines outside local git/pytest workflows.
- Unrestricted network crawling without target allowlist approval.
- Automated ZAP / DAST security scanner integrations.

---

## Further Notes

- **Tracker Convention:** Issues are tracked as individual files under `.scratch/qa-cc-remediation/issues/` numbered `01` to `30`, in full accordance with `docs/agents/issue-tracker.md`.
- **Token Preservation:** T-19 context pruning is critical to ensure multi-agent runs remain within viable token limits before running Phase 9 benchmarks.
