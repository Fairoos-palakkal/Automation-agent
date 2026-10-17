# Agentic QA Command Center — Phase-Based Implementation Plan

*Base: the Automation-agent repo (PRD Phases 0–3 as code) and the 16 Oct 2026 implementation audit (F-01 to F-24) · Route: the /ask-matt flow · 17 Oct 2026*

## 1. Where the project actually is

The scaffolding is good. The module seams (LLMClient, ToolGateway, RunState, TraceWriter), FakeProvider-first testing, the Evidence/Finding models, ADR-0001 and the ground-truth AST test are all worth keeping. The audit counted 114 green unit and contract tests.

The run path does not yet deliver the project's core promise. The headline problems, all from the audit:

- The benchmark table is hard-coded literals, not measured (F-01).
- `VerdictEngine.evaluate` is never called on the run path, and Challenger and Crawler are never called by the CLI (F-02, F-18).
- The allowlist is a substring check, redirects and in-page clicks escape it, secrets are never scrubbed on the live path, and the report renders evidence as raw HTML (F-04, F-05, F-09, F-10).
- Agent prompts carry Juice Shop and Noshery specifics, so recall proves the prompt rather than the agent (F-07).
- Replan is unreachable and the run-level budget is never counted (F-11).

So this plan is **not** "build the next feature". It is: make what exists true, wire the promise end to end, then measure honestly. PRD Phases 0–3 exist as code; they do not yet exist as behaviour.

*Source note: findings, file references and evidence labels (\[V\] verified by execution, \[C\] by reading, \[S\] suspected) come from the audit. This plan did not re-run them, so confirm a finding with a failing test before fixing it. That is what the TDD flow does anyway.*

*Coverage check (17 Oct 2026): the plan was compared item by item against the audit. Tickets T-01, T-04 to T-08, T-10, T-12 to T-14, T-16, T-18 to T-23, T-25 to T-27 were widened in place, T-20 and T-23 gained blockers, and T-30 was added. Nothing was removed.*

## 2. What /ask-matt says about this situation

The router asks a few questions in order. Here are the answers for this repo.

**You have a working directory.** Use `/grill-with-docs`, not `/grill-me`. It is stateful and writes to `CONTEXT.md` and ADRs, which this repo already has.

**Is it foggy enough for `/wayfinder`?** No. Wayfinder is for a greenfield or huge effort where the way is not visible. The audit already is the map, with 24 findings, dependencies and a P0–P3 roadmap. Using wayfinder here would be ceremony.

**Is it `/triage` material?** No. Triage is for issues you did not create. These findings are yours, and tickets from `/to-tickets` are already agent-ready.

**Does any question need a runnable answer?** Yes, one: *can a fresh-context replay actually reproduce a planted defect?* (F-19, the audit says gateway-only replay can never confirm). That is a `/prototype` detour, bridged by `/handoff` out and back. A second prototype (what a live dashboard should look like) only exists if the stretch phase is approved.

**Is it a multi-session build?** Yes. The route is `/to-spec`, then `/to-tickets`, then `/implement` per ticket with `/clear` between tickets. `/implement` drives `/tdd` internally and closes with `/code-review` (Standards + Spec) before committing.

**Standalone helpers that apply:**

- `/diagnosing-bugs` if F-19 resists a first look (build a one-command red loop first, then fix).
- `/improve-codebase-architecture` once F-22 lands (three copies of the agent loop become one).
- `/wait-what` any time a message does not land.

**Precondition.** Run `/setup-matt-pocock-skills` (issue tracker, triage labels, doc layout). `CLAUDE.md` says the skills are installed in `.agents/skills/`, but `.agents/` was not in the zip, so confirm it exists in the real repo.

**Context hygiene.** Keep grill, spec and tickets in one unbroken context window. Do not compact or clear until after `/to-tickets`. If you approach the smart zone (about 150k tokens) first, `/compact` at the nearest phase boundary. Each `/implement` then starts fresh from its ticket.

## 3. Phase map

Phases continue the repo's numbering. Priorities map to the audit roadmap.

| Phase | Goal | Audit priority | Findings | Tickets |
| --- | --- | --- | --- | --- |
| 4 — Align | Settle decisions, fix the glossary, cut the spec and tickets | Prep | D4, scope conflicts | none (docs only) |
| 5 — Stop the bleeding | Nothing false published, nothing unsafe on the run path | P0 | F-01, F-02 (part), F-04, F-05, F-09, F-10, F-14 | T-01 to T-07, T-30 |
| 6 — One loop, real evidence | Shared loop, run identity, captured Evidence, replayable steps | P1 foundation | F-22, F-20, F-03 | T-08 to T-11 |
| 7 — Verdicts from code | Engine, replay and Challenger wired into `run` | P1 | F-16, F-19, F-02 | T-12 to T-15 |
| 8 — Agents that really work | Black-box prompts, working orchestrator, observation, permissions | P1 | F-07, F-11, F-12, F-13, F-06, F-08, F-17, F-21 | T-16 to T-22 |
| 9 — Measure honestly | Trustworthy scoring, coverage, sealed held-out, real benchmark | P1 + P2 | F-15, F-18, F-23, F-01 (full) | T-23 to T-26 |
| 10 — Ship, then stretch | Packaging and hygiene; dashboard and paste-any-site only behind an ADR | P3 | F-24, optional | T-27 to T-29 |

Phases 5 to 9 are the critical path. Phase 10 is optional.

## 4. Phase 4 — Align (no code)

**Goal:** enter implementation with one shared language, resolved decisions and an agent-ready backlog.

**Flow:**

1. `/setup-matt-pocock-skills`.
2. `/grill-with-docs` on the audit. Feed it `files/PRD.md`, the audit doc, `CONTEXT.md` and the ADRs.
3. Optional detour: `/handoff` to a prototype directory, `/prototype` for the replay question, `/handoff` back.
4. `/to-spec`, then `/to-tickets` (tickets in section 5 to 10 are the starting breakdown to quiz against).

**Before step 1:** settle the doc layout. Put `PRD.md` and `CONTEXT.md` where `CLAUDE.md` says they are (repo root), pick one of the two diverging `CLAUDE.md` copies (root vs `files/`), and diff the PRD PDF against `files/PRD.md`. `/grill-with-docs` writes `CONTEXT.md` and the ADRs, so the layout has to be fixed first.

**Decisions to settle in the grill:**

- **D4, the three Juice Shop Objectives.** Suggested: authentication, basket/checkout, search/input handling. Needed before T-23, because the scoreboard delta is scoped to these Objectives.
- **Dashboard and paste-any-site.** The PRD lists a live dashboard as a non-goal and `CLAUDE.md` has a scope guard against it. Arbitrary targets conflict with the mandatory allowlist (PRD §10). Decide: keep both out, or amend the PRD and record an ADR first. Default recommendation: out of the critical path, in Phase 10 only if approved.
- **Honesty policy for published numbers.** Proposal: nothing in README, PORTFOLIO or the CV that `qa-cc results` did not generate, with run ids and commit hash.
- **Token plan.** The PRD sized the reserve at about 300K tokens, or 1–3 benchmark runs. The audit measured 326,669 tokens for one Noshery run and 981,598 for the Juice Shop run. Seven Own Site runs (3 baseline, 3 multi-agent, 1 held-out) at the lower figure is roughly 2.3M tokens before context pruning. Either T-19 cuts this hard first, or D5 (a few dollars of top-up) gets used, or cassettes cover more of the work.

* **Held-out re-seal.** DEFECT-007 was implemented in `mock_api.py` during Phase 2, while tuning, so the held-out set is no longer blind. Decide: write fresh held-out defects (at least replacing DEFECT-007) and keep only their hash in the repo. Needed before T-25.

**New vocabulary to add to `CONTEXT.md`** (the glossary forbids synonyms, so name these once): Target Profile, StepLog, FindingVerifier, Replayer, Run Directory, Sealed Held-out Set.

**ADRs to write:** ADR-0003 (verdict pipeline: engine then replay then finalize, scorer never writes verdicts) and ADR-0004 (results are generated, never typed). ADR-0005 only if the dashboard or arbitrary-target mode is approved.

**Phase boundary after `/to-tickets`:** nothing in this window is needed by implementation because each ticket is self-contained. Use `/clear`. If the window is near 150k, `/compact` before `/to-tickets` instead.

**Exit:** `CONTEXT.md` updated, ADR-0003 and ADR-0004 committed, D4 and the held-out re-seal decided, backlog published with blocking edges.

## 5. Phase 5 — Stop the bleeding (P0)

**Goal:** the repo claims nothing it cannot show, and the safety rules hold on the real run path.

**Order of work:** T-01, T-02 and T-04 to T-07 have no blockers, so the frontier is wide. Do T-01 first because the README and portfolio are what an interviewer opens.

| ID | Ticket (tracer bullet) | Blocked by | Verifiable by | Size |
| --- | --- | --- | --- | --- |
| T-01 | `qa-cc results` aggregates `runs/<config>/<run_id>/score.json` and exits non-zero with "no scored runs found" when there are none. Literals deleted. README and PORTFOLIO numbers removed, plus every claim the code cannot demonstrate (cryptographic or append-only trace, automatic scrubbing, "all findings pass VerdictEngine and Challenger", replay and hallucination claims). Docs name LLM\_API\_KEY, not BAI\_API\_KEY. results prints mean and spread once a config has several runs (F-01) | none | Empty-directory test exits 1; a fixture score.json change changes the table; README and PORTFOLIO are clean of the listed claims | M |
| T-02 | One exact-host allowlist function (urlsplit, scheme http/https, no userinfo, exact hostname or host:port) shared by Gateway and Crawler (F-04) | none | Parametrised bypass tests: `localhost.evil.com`, `evil.com/?next=localhost`, `localhost@evil.com`, IPv6, uppercase, trailing dot, port mismatch | S |
| T-03 | HTTP tool follows redirects manually (max 5 hops, each re-checked), caps body size. Playwright `context.route` aborts disallowed hosts and traces the denial (F-05) | T-02 | 302-to-disallowed-host test; external link click blocked and traced in e2e | M |
| T-04 | Report escapes every interpolated value and carries a CSP meta tag (F-10) | none | A `<script>` in evidence renders inert; the report has a CSP meta tag | S |
| T-05 | Scrubbing enabled on the live path: secrets from env (LLM\_API\_KEY) plus JWT-shaped strings, Authorization headers and Set-Cookie values, in trace, findings and report (F-09) | none | Grep of the output directory finds no key or JWT | S |
| T-06 | Fail fast: missing API key, missing browser, malformed tool args each produce a clear error and non-zero exit. Add python-dotenv. Retry 429, 5xx and timeouts with backoff. Label mock runs in the report header (F-14) | none | One test per failure mode (no key, no browser, bad args, 429 retry, mock label) | S |
| T-07 | Remove verdict writing from `handle_score`. Report labels findings "unverified" until a real verdict exists. Remove the --update-report option (F-02 part) | none | `grep -n 'Verdict(' src benchmark` finds none in scoring or CLI | S |
| T-30 | Repo safety sweep: scan git history and .env handling for committed keys and rotate any found; add .gitignore (moved up from T-27); run on a real machine the two e2e tests that failed in the audit sandbox (no Chromium) and record the result as the verified baseline (audit section 8) | none | Git-history key scan clean or keys rotated; .env, egg-info, \_\_pycache\_\_ and .DS\_Store ignored; e2e pass or fail recorded | S |

**Boundary:** `/clear` between tickets. `/code-review` per ticket via `/implement`.

**Gate (Phase 5):**

- `qa-cc results` in an empty directory exits non-zero.
- Lookalike-host and redirect tests pass.
- No secret or JWT appears anywhere in a run's output directory.
- The report escapes all untrusted strings.
- README and PORTFOLIO contain no number the code did not generate. **If the old numbers are on your CV, remove them now, before this phase is even done.**

* No key in git history, or any key found is rotated, and `.gitignore` is in place.
* The two e2e tests the audit could not run have been run on a real machine and the result is recorded.

## 6. Phase 6 — One loop, real evidence

**Goal:** one agent loop, attributable runs, and Findings built from what tools actually observed.

This phase is the enabler. The audit says shared AgentLoop, StepLog and run identity unblock most of what follows.

| ID | Ticket (tracer bullet) | Blocked by | Verifiable by | Size |
| --- | --- | --- | --- | --- |
| T-08 | **Expand:** shared `AgentLoop` + `StepLog` beside the old loops; Baseline Agent migrated onto it. The loop replaces the silent catch-all that ends a run with llm\_error, tool\_error and invalid\_args outcomes: each is traced and sets the run status, and malformed tool-arg JSON is rejected instead of run as {} (F-22, F-14) | Phase 5 gate | Existing baseline tests still green; a failing LLM call yields llm\_error status plus a trace entry | L |
| T-09 | **Migrate and contract:** Browser and API agents move to `AgentLoop`; the duplicated loops are deleted (F-22) | T-08 | Roughly 500 fewer lines; all existing tests green | M |
| T-10 | Run identity: `run_id`, `runs/<config>/<run_id>/` layout, `TraceEntry` schema with served `model_id` on every entry, denied calls traced, and every tool call traced in a finally block. Hash-chain the trace (seq plus prev\_hash), or delete the cryptographic and append-only claim from the docs (F-20) | T-08 | Schema test; trace totals match the token counts in the run | M |
| T-11 | Structured findings: `report_finding {summary, expected, actual, selector/url, step_ids}`. The runtime builds Evidence from the last real observation; model-typed `evidence_content` is ignored (F-03) | T-08, T-10 | Fabricated evidence is ignored; every finding has non-fingerprint steps | L |

F-22 is a classic expand–contract change, so it is sequenced that way rather than forced into one oversized ticket.

**Boundary:** `/clear` between tickets. After T-09, run `/improve-codebase-architecture` as a spare-moment survey. It may generate an idea worth taking back to `/grill-with-docs`.

**Gate (Phase 6):** every finding in a fresh `findings.json` has captured Evidence and replayable steps. A baseline finding is replayable. Every trace entry carries a model id.

## 7. Phase 7 — Verdicts from code

**Goal:** make ADR-0001 true. Verdicts come from the engine and replay, and only from there.

| ID | Ticket (tracer bullet) | Blocked by | Verifiable by | Size |
| --- | --- | --- | --- | --- |
| T-12 | Verdict Engine selector semantics: real CSS selectors (not only `#id`), a status-code rule, `FLAKY` and `PASS_AFTER_RETRY` produced by bounded retry; URLs normalised (trailing slash); text matching that handles nested markup; no\_console\_errors no longer fails on any console message such as a favicon 404 (F-16) | none in phase | Unit tests: `button.buy` present gives FAIL; a retry that passes is recorded as FLAKY, never silent PASS; parametrised tests for class, attribute, nested text and trailing slash | M |
| T-13 | Replayer in a fresh browser context, driven by StepLog. Challenger can replay a baseline finding and downgrade (never upgrade) to INCONCLUSIVE. It needs a real browser, so it is tested as e2e (or with a fake driver), never in the default unit run (F-19) | T-11 | Replay confirms a planted defect; a non-reproducible one is downgraded | L |
| T-14 | FindingVerifier: derive an `AssertionRule` from structured fields, run the engine, run replay, `finalize_verdict`, write verdict plus reason to trace and findings.json, and render verdict reason, step list and trace link on each report card (F-02) | T-12, T-13 | Integration test with FakeProvider and a local page: verdict type comes from the engine; a finding whose assertion passes becomes INCONCLUSIVE | M |
| T-15 | E2E on Own Site: a real run confirms DEFECT-004 through engine plus replay | T-14 | `grep -n 'Verdict(' src benchmark` shows creation only in `verdict/` and challenger code | M |

T-13 is the riskiest ticket in the plan, which is why the optional `/prototype` detour in Phase 4 targets it. If it resists a first look, use `/diagnosing-bugs`.

**Boundary:** after T-15, send `/code-review` of the whole phase to a subagent (AFK, read-only report) while you review the run output yourself. T-15 needs Chromium, so run it on your machine, not in a sandbox.

**Gate (Phase 7):** a Challenger replay in a fresh context confirms one planted defect and downgrades one non-reproducible finding. Every finding in a run has a verdict from `finalize_verdict`.

## 8. Phase 8 — Agents that really work

**Goal:** the multi-agent configuration is real, black-box, observable and bounded, so the baseline vs multi-agent comparison means something.

| ID | Ticket (tracer bullet) | Blocked by | Verifiable by | Size |
| --- | --- | --- | --- | --- |
| T-16 | Target Profile instead of hard-coded prompts. Juice Shop selectors, endpoints, the SQLi payload and Noshery bug classes removed from prompts. Profile is traced and used by both configurations; scores are reported with and without the profile (F-07) | none in phase | Grep test finds no target-specific strings in prompt modules | M |
| T-17 | Orchestrator: run-level RunState charged, `failed` and `loop_terminated` handled, replan at most 2 and refused the third (traced), `prior_findings` actually read, fresh browser context per Task (F-11) | T-09 | The F-11 test list; third replan refused | L |
| T-18 | Console errors and failed requests visible to agents, wrapped in the untrusted-content fence (F-12) | T-09 | The catalog.html TypeError is observed in a live-style test | M |
| T-19 | Context pruning, interactive-element index, model-call and wall-clock budgets; max\_turns derived from the budget (F-13) | T-08 | 25-turn test shows roughly linear prompt growth; multi-agent Own Site run fits the token reserve | L |
| T-20 | Per-agent caller permissions; the gateway owns the screenshot path (F-06) | T-09, T-10 | Browser caller invoking `http_request` raises PermissionRequired; screenshots unique per step | S |
| T-21 | Fence hardening (per-run random fence name, fence tokens stripped from content, one system-prompt paragraph saying fenced text is data, wrapper applied to HTTP bodies and console output) plus a real injection fixture test (F-08) | T-03 | The injection test fails when the gateway check is removed; a break-out string cannot terminate the fence | M |
| T-22 | Loop detector catches ABAB patterns with real recovery (F-17); planner accepts fenced JSON, typed budgets, empty-plan handling, 1 to 6 task and unique-id validators, parse error appended to the retry message, integer budget split with the sum at most the total (F-21) | T-08 | ABAB, ABCABC and recovery tests ending in loop\_terminated; fenced-JSON, empty-plan, duplicate-id and budget-sum tests | M |

T-19 matters for budget as much as quality. The audit saw 46K-token prompts by turn 40, and the token reserve is the project's tightest constraint.

**Boundary:** `/clear` between tickets. Rule 4 of `CLAUDE.md` (application content is untrusted) governs T-21, so write the failing injection test first and confirm it goes red.

**Gate (Phase 8):** prompts contain no target-specific strings; the orchestrator enforces the run budget; the third replan is refused; console errors are observable; prompt growth is about linear.

## 9. Phase 9 — Measure honestly

**Goal:** a results table that every reviewer can reproduce from committed run artifacts.

| ID | Ticket (tracer bullet) | Blocked by | Verifiable by | Size |
| --- | --- | --- | --- | --- |
| T-23 | Scoring Harness rewrite: `score.json` with recall, triaged precision, replay rate, unsupported findings, coverage, cost per confirmed finding. Juice Shop scored as a scoreboard before/after delta. Refuses mixed-model comparisons using model ids from traces. Lives in src/qa\_cc/scoring (move it out of benchmark/scoring first, so it is not rewritten twice). Matches on the frozen matcher objects, not free-text substrings. Raises when the scoreboard is unreachable instead of reporting recall 0.0. The Juice Shop delta is limited to the D4 Objectives. Defines how findings are triaged for precision: who labels them and where the labels are stored (F-15) | T-10, T-11, T-14, D4 decided | Golden-file tests; mixed-model comparison refused; an unreachable scoreboard raises | L |
| T-24 | Crawler on Playwright (SPA-aware) feeding Coverage into `score.json` (F-18) | T-02, T-23 | `score.json` has a coverage field computed from a crawl | M |
| T-25 | Sealed held-out set: re-seal first (DEFECT-007 was visible during tuning, so write fresh held-out defects), split defects.tuning.json from the sealed held-out file and commit only its hash; lock file, one-time `--final`, ground-truth isolation test widened beyond `agents/` and `llm/` (F-23) | T-23 | A second `--final` is refused; isolation test covers all of `src/` | M |
| T-26 | The real benchmark: 3 baseline and 3 multi-agent runs on the tuning set, one held-out run, the three Juice Shop Objectives from D4. README table generated by a script, citing run ids and commit hash. Curated runs are committed under examples/ so a reviewer can regenerate the table (F-01, F-15) | T-15, T-17 to T-25 | `qa-cc results` regenerates the published table exactly | L |

T-26 is human-in-the-loop, not AFK. It needs Docker for Juice Shop, a real browser, the pinned bench model, and possibly the D5 top-up. Do not start it before T-19 has reduced tokens per run.

**An honest result is a good result.** The PRD itself says a "no improvement" outcome is publishable if measured honestly. Multi-agent costing more for the same recall is a legitimate finding, and it reads far better than a suspiciously perfect table.

**Gate (Phase 9):**

- 3 baseline plus 3 multi-agent runs exist, with mean and spread.
- Held-out was scored once, behind a lock.
- Every number in README, PORTFOLIO and the CV is produced by `qa-cc results`.
- ADR-0002 records one live contract run.

## 10. Phase 10 — Ship, then stretch

| ID | Ticket | Blocked by | Verifiable by | Size |
| --- | --- | --- | --- | --- |
| T-27 | Packaging and hygiene: `.gitignore` (started in T-30, finish here), justfile with the real test, lint, run and score commands (fill the empty Commands section of `CLAUDE.md`), dependency extras, remove duplicate docs (`files/` copies, stray PNGs and uncurated run directories; curated runs stay under examples/), `pip install .` then `qa-cc run`, `score`, `results` from any directory (F-24) | Phase 9 gate | A clean clone contains no generated files or duplicate docs | M |
| T-28 | Serve the mock FastAPI backend from the CLI and let Own Site pages call it, so the API Agent target is real (F-24) | none | API Agent e2e hits the live mock | M |
| T-29 | **Stretch, gated:** live dashboard and paste-any-site mode | ADR-0005 approved first; T-26 done | Whatever the ADR specifies | L |

**Why T-29 sits last and behind an ADR.** You want a clickable live view and the ability to paste any site, including Juice Shop API testing. Both are reasonable portfolio features. But the PRD lists the dashboard as a non-goal, and arbitrary targets break the mandatory allowlist that protects you from a prompt-injected page driving the browser off-target. If you approve it, do it properly: amend the PRD, write ADR-0005, and keep the allowlist as an explicit user-confirmed addition per Run rather than removing it. Run `/prototype` first to settle what the UI should look like.

The Juice Shop API-testing piece does not need to wait. It is already covered by the API Agent, the exact-host allowlist (T-02) and the 3 Objectives (T-26).

Deferred on purpose: accessibility-tree snapshots via Playwright (audit P3, optional, F-13). The interactive-element index in T-19 covers the need for now.

## 11. Dependency view

The critical path, in order:

- T-02 then T-03, then T-21 (allowlist, then redirects, then fence tests).
- T-08 then T-10 and T-11, then T-13, then T-14, then T-15 (loop, then run identity and evidence, then replay, then verifier, then e2e).
- T-08 then T-19, then T-26 (pruning must land before the expensive benchmark).
- T-23 then T-24 and T-25, then T-26.

Tickets that parallelise freely: T-01, T-04, T-05, T-06, T-07, T-30 in Phase 5; T-12, T-16, T-28 elsewhere, and T-20 once T-10 lands.

## 12. Working rules for every ticket

These come from `CLAUDE.md` and the ask-matt flow, restated because they are the ones most likely to slip.

- **Red first.** Write the failing test, run it, see it fail, then implement. One behaviour per commit.
- **Unit tests stay deterministic:** no network, no real LLM, no real browser. Use FakeProvider and cassettes. `e2e` and `live` stay out of the default run.
- **Glossary words only.** Use Finding, Evidence, Verdict, Challenger and the rest. No "evaluator" or "bug report".
- **A new term** goes through `/grill-with-docs` into `CONTEXT.md` before it appears in code.
- **Phase boundaries** follow the tree in order: Continue, then `/clear`, then `/handoff` (only for a new harness, directory or colleague; `GEMINI.md` suggests you may switch harnesses), then subagent, then `/compact` as the default fallback.
- **Scope guard:** nothing from the PRD non-goals without an ADR. If a ticket seems to need one, stop and ask.

## 13. Blunt notes

- **The fake table is the whole ballgame.** F-01 is not a bug, it is a credibility problem. A reviewer who opens `cli.py` and finds literals will discount everything else, including the parts that are genuinely good. Fix it before anything else, and take the numbers off your CV today.
- **The temptation is the dashboard.** A live view feels like progress and is fun to build, but the verdict pipeline is not wired. A pretty dashboard over unverified findings is a prettier version of the same problem.
- **Phases 7 and 9 are where the portfolio value is.** Employers hiring for agentic testing roles care that verdicts are deterministic and that numbers are measured. That is exactly what these phases deliver, and it is rarer than another agent demo.
- **Do not skip T-19.** Running the benchmark with 46K-token prompts will eat your token reserve before you get three clean runs per configuration.

## 14. Definition of done

The plan is complete when the audit's final acceptance checklist is fully ticked. In short:

- Integrity: `results` fails on empty, all published numbers are generated, and no doc claim goes beyond what the code demonstrates.
- Safety: allowlist, redirects, scrubbing, escaping, fence and permissions all tested.
- Verdicts: every finding has captured Evidence, replayable steps and a code-produced verdict.
- Agents: black-box prompts, enforced budgets, working replan, observable console.
- Measurement: all PRD §9 metrics in `score.json`, 3 + 3 runs, one sealed held-out run, Juice Shop scored as a scoreboard delta.
- Engineering: unit suite green, Own Site and multi-agent e2e executed with a real browser, and a clean clone installs and runs from any directory.
