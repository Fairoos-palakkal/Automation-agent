# Agentic QA Command Center — PRD

Revision: 2026-10-14 · Supersedes: Revised PRD v2 · Status: baseline for TDD implementation planning
Vocabulary: see `CONTEXT.md`. Terms below (Objective, Target, Run, Finding, Evidence, Verdict, etc.) are defined there.

## 1. Summary

A CLI-first system that takes a natural-language **Objective**, explores a web **Target** black-box using permission-gated tools, captures **Evidence** on every action, and reports **Findings** whose **Verdicts** come from deterministic checks. The LLM proposes what to investigate; deterministic code establishes what happened.

It is built in two stages and measured: first a single **Baseline Agent** (Day 1), then a multi-agent split into **Planner + Browser Agent + API Agent**, plus a **Challenger** (Days 2-3). The multi-agent version is compared against the baseline on the same benchmark.

**Purpose:** portfolio piece for entry-level agentic testing / AI QA roles. **Timebox:** 3 days.
**Claim to prove with numbers:** whether splitting into role-specific agents improves results (context bloat, planning quality) and at what cost. A "no improvement" result is still publishable if measured honestly.

## 2. Non-goals

Regression store, GitHub Actions / CI, ZAP integration, SSRF controls beyond the target allowlist, plugin system, live dashboard, RBAC, hosted SaaS, multiple provider-specific adapters, arbitrary-target security scanning, an LLM evaluation agent at runtime.

## 3. Principles

1. The LLM never decides a Verdict. Deterministic assertions and replay do.
2. Evidence first: no Finding without attached Evidence.
3. Black-box: agents get a Target URL and an Objective, nothing about planted defects.
4. All tool access goes through the Tool Gateway.
5. Application content (DOM, text, responses) is untrusted data, never instructions.
6. Measure before you split: the Baseline Agent comes first and is the yardstick.
7. Everything is traced: model calls, tool calls, Evidence, Verdicts, tokens, served model ID.

## 4. Targets

**4.1 Own Site.** A frontend-only site we build, with at least 8 **Planted Defects** across categories (form validation, broken navigation or links, state/logic errors, accessibility, console errors, visual/layout). Each defect has an ID and an automatic matcher (page + condition) stored under `benchmark/ground_truth/`. The list is written and frozen **before any agent code**. 5 defects are the tuning set; 3 are held out and never inspected while tuning. Agent code and prompts must never read `benchmark/ground_truth/`.

**4.2 OWASP Juice Shop.** Run locally in Docker, isolated, localhost-only, covered by the target allowlist. 3 scoped Objectives (e.g. authentication, basket/checkout, search/input handling; final choice is open decision D4). Ground truth is Juice Shop's challenge scoreboard, read only by the Scoring Harness. Juice Shop solutions are widely public and likely in model training data, so "found it" alone is weak evidence; Findings are also scored on Evidence and replay.

## 5. Architecture

```
Objective -> Planner -> Plan (Tasks) -> Browser Agent / API Agent
          -> Tool Gateway -> Playwright tools / HTTP tool
          -> Evidence -> Verdict Engine -> Findings -> Challenger
          -> JSONL Trace + static HTML Report
```

Day 1 replaces Planner + Browser Agent + API Agent with a single Baseline Agent using the same gateway, tools, and Verdict Engine.

| Component | Responsibility | LLM? |
|---|---|---|
| LLM Client | One OpenAI-compatible client (base URL + model per profile), tool-calling, token accounting, output-schema validation with bounded retry | no |
| Tool Gateway | Only route to tools: allowlist, permissions, budgets, secret scrubbing | no |
| Browser tools | navigate, click, fill, compact page snapshot, screenshot, console and network capture | no |
| HTTP tool (Day 2) | Requests to allowlisted Target origins only; request/response recorded as Evidence | no |
| Verdict Engine | Deterministic assertions (element state, text, URL, status code, console errors) | no |
| RunState | Passed through every agent turn: budgets, history fingerprints, Findings so far | no |
| Trace + Report | JSONL trace, static HTML report | no |
| Crawler | Non-LLM exploration that produces the reference inventory for Coverage | no |
| Scoring Harness | Offline comparison of Findings against Planted Defects or the Juice Shop scoreboard | no |
| Baseline Agent, Planner, Browser Agent, API Agent, Challenger | See section 6 | yes |

## 6. Agent contracts (Days 2-3)

- **Planner:** input is Objective + Target metadata; output is a **Plan** (JSON validated against a schema) of Tasks, each with `assignee` (browser or api), `goal`, scope hints, and a budget. No direct tool access. May replan a bounded number of times (D2).
- **Browser Agent / API Agent:** each has its own context, tool set, and budget. It receives only its Task, not the full history. It returns Findings with Evidence references and the recorded steps, not transcripts. This is the mitigation for context bloat.
- **Challenger:** input is a Finding. It may request a deterministic replay of the recorded steps or flag missing Evidence. It may downgrade a Finding to INCONCLUSIVE and can never upgrade one or set a Verdict.
- **Final Verdict on a Finding:** deterministic assertion result plus replay result.

## 7. Reliability

- **Budgets per Run** (calibrate during Phase 0): actions, model calls, wall-clock time, and tokens, each enforced globally and per agent. Starting point: 25 actions per agent, 3 minutes, and a token cap sized to the available token reserve.
- **Loop detection:** action fingerprint = hash(tool + normalized args + URL); observation fingerprint = hash(relevant DOM/state). Three repeated pairs trigger recovery: re-observe, validate state, bounded retry or alternate locator, then continue or terminate INCONCLUSIVE.
- **Retries:** bounded; a retry that passes is recorded as PASS_AFTER_RETRY / FLAKY, never silently PASS.
- **Malformed model output:** schema-validate, retry at most twice, then fail the step and record it.
- **Snapshots** are compacted (accessibility-tree style, truncated) to cap tokens per step.

## 8. Providers and token budget

- One OpenAI-compatible client. Profiles set base URL, model, and settings.
- **dev profile:** Gemini free tier or OmniRoute; the served model may vary; used for iteration only.
- **bench profile:** one pinned model, Qwen3.8-Flash via B.AI (confirm the exact model ID in the B.AI catalog), thinking off or low. The trace records the served model ID and token counts, and the Scoring Harness refuses to compare Runs with different bench models.
- **Token reserve:** about 300K B.AI tokens. A full multi-agent Run may use roughly 100K-300K tokens (estimate), so treat the reserve as 1-3 benchmark Runs. Mitigations: FakeProvider for TDD, record/replay cassettes, snapshot compaction, thinking off. A small paid top-up is the fallback (D5).
- OmniRoute is optional and dev-only. Before relying on it, run a spike: about 60 tool-calling requests in 2 minutes, recording failure rate and malformed-JSON rate.

## 9. Evaluation

The Scoring Harness runs offline after a Run and never feeds back into the agents.

| Metric | Definition |
|---|---|
| Recall | Planted Defects matched / planted (automatic matchers); Juice Shop: scoreboard challenges solved |
| Precision | Findings matching nothing are hand-triaged once: real unplanted bug or false positive |
| Replay rate | Share of Findings whose recorded steps replay and reproduce the failing check |
| Unsupported Findings | Findings lacking Evidence or failing replay (target: 0 in published reports) |
| Coverage | Crawler-discovered pages, forms, and links exercised / total |
| Cost | Actions, model calls, and tokens per confirmed Finding |
| Variance | 3 Runs per configuration; report mean and spread |

Protocol: Baseline vs multi-agent on the same Own Site tuning set, then report held-out results once. Initial targets (revisit after the baseline): at least 50% recall on held-out defects, 0 unsupported Findings.

## 10. Safety

Target allowlist is mandatory (Own Site and local Juice Shop only). Observed DOM/text is delimited and cannot change system policy, target, permissions, or budgets. Secrets are scrubbed from traces and never committed. Destructive tools require explicit permission. One small prompt-injection fixture page is included in Phase 3.

## 11. Phases

**Phase 0 (first hours): foundations and spike.** LLM Client + FakeProvider, JSONL Trace, RunState, budget enforcer, OmniRoute/B.AI spike, defect list and matchers frozen. Exit: spike result recorded, contract tests green, ground truth frozen.

**Phase 1 (Day 1): Baseline Agent.** Tool Gateway, Playwright tools, Evidence capture, Verdict Engine, loop detection and recovery, CLI, static report, Own Site, Scoring Harness, Crawler. Exit: a single-agent Run on Own Site produces a trace, Evidence, and a static report with at least one replayable Finding, plus baseline Recall and Coverage numbers. If not green, Phase 2 does not start.

**Phase 2 (Day 2): multi-agent.** Plan schema, Planner, Browser Agent, API Agent with the HTTP tool. Exit: Plan validates, both sub-agents run under separate budgets, and baseline vs multi-agent numbers exist on the tuning set.

**Phase 3 (Day 3): Challenger, Juice Shop, polish.** Challenger with replay, 3 Juice Shop Objectives scored via the scoreboard, prompt-injection fixture, README and demo. Exit: results table including held-out defects.

**Cut order if behind schedule:** prompt-injection fixture first, then Challenger, then reduce Juice Shop to one Objective.

## 12. Test strategy (input for the TDD plan)

- Deterministic unit tests, no network and no real LLM: fingerprinting, loop detection, budget enforcer, Verdict Engine, scoring matchers, Plan schema validation, trace writer, secret scrubbing, allowlist.
- LLM-facing code is tested through FakeProvider and recorded cassettes.
- Contract tests for the LLM Client against FakeProvider and one recorded real response per profile.
- A test that fails if any agent module can read `benchmark/ground_truth/`.
- Browser e2e on Own Site and live-LLM runs are marked `e2e` / `live` and excluded from the default test run.

## 13. Decisions

Decided (2026-10-14):

- **D1 Stack:** Python 3.11+, Playwright, Pydantic, pytest.
- **D2 Replan policy:** Planner may replan at most 2 times, only from sub-agent reports.
- **D3 API target for Own Site:** add a small FastAPI mock backend with 2-3 planted API defects, so the API Agent has a target where we control ground truth.
- **D5 Token top-up:** a few dollars of top-up is allowed if the B.AI reserve runs out.
- **D6 Shared state between agents:** Findings + Evidence references only, never transcripts.
- Verdicts are deterministic and there is no runtime evaluation agent (see `docs/adr/0001-deterministic-verdicts-no-evaluation-agent.md`).

Still open:

- **D4 Juice Shop Objectives:** pick 3 before Phase 3. Suggested: authentication, basket/checkout, search/input handling.

## 14. Suggested repo layout

```
CLAUDE.md  CONTEXT.md  PRD.md  docs/adr/
src/qa_cc/{llm,gateway,tools,verdict,agents,trace,report,crawler}/
benchmark/{own_site,ground_truth,scoring}/
tests/{unit,contract,e2e}/
```
