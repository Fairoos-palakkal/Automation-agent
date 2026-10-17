# Agentic QA Command Center

A system that takes a natural-language testing objective, explores a web target black-box, and reports evidence-backed defect findings. An LLM proposes what to investigate; deterministic checks establish what actually happened.

## Language

### Run and subject

**Objective**:
The natural-language goal a Run is given, such as "test the checkout flow". It never contains hints about specific defects.
_Avoid_: Prompt, task, ticket

**Target**:
The application under test: either our own site with planted defects, or an isolated OWASP Juice Shop instance.
_Avoid_: SUT, site, app (when precision matters)

**Run**:
One complete attempt to pursue one Objective against one Target, from start to final report.
_Avoid_: Session, execution, job

**Target Profile**:
A declared file containing target-specific metadata and scope hints, recorded in the trace and supplied identically to baseline and multi-agent configurations to preserve black-box prompt purity.
_Avoid_: Target config, site hints, prompt hints

**Run Directory**:
An attributable filesystem directory structured as `runs/<config>/<run_id>/` storing `trace.jsonl`, `findings.json`, and `score.json` for a single Run.
_Avoid_: Output folder, run output, artifact dir

### Agents and Execution

**Agent**:
A component with its own LLM loop, context, tool set, and budget.
_Avoid_: Bot, worker

**Baseline Agent**:
The single Agent that does all the work in the first stage. It is the yardstick the multi-agent setup is measured against.
_Avoid_: Executor, single agent

**Planner**:
The Agent that turns an Objective into a Plan and assigns each Task to an Agent. It has no direct tool access.
_Avoid_: Orchestrator, supervisor, manager

**Plan**:
A structured list of Tasks produced by the Planner for one Run.
_Avoid_: Test plan, strategy

**Task**:
One unit of work in a Plan, assigned to exactly one Agent, with its own goal and budget.
_Avoid_: Step, job, ticket

**Browser Agent**:
The Agent that carries out Tasks through browser tools.
_Avoid_: Playwright agent, UI agent

**API Agent**:
The Agent that carries out Tasks through HTTP tools.
_Avoid_: HTTP agent, REST agent

**Challenger**:
An Agent that disputes a Finding by requesting a replay of the recorded steps or flagging missing Evidence. It may downgrade a Finding to INCONCLUSIVE but never upgrade one.
_Avoid_: Evaluator, evaluation agent, judge

**StepLog**:
An append-only per-run sequence of executable actions and observations recorded by tools with unique step IDs, used for reproduction and replay.
_Avoid_: Action log, history, event log

**FindingVerifier**:
The deterministic component that derives an AssertionRule from structured finding fields, invokes the Verdict Engine on live state, triggers Replayer, and writes the finalized verdict.
_Avoid_: Evaluator, validator, verification agent

**Replayer**:
A deterministic harness that executes recorded steps from a StepLog within a fresh, isolated browser context to verify defect reproducibility.
_Avoid_: Playback, re-executor, test runner

### Results

**Finding**:
A claim that the Target has a defect, together with the Evidence supporting it.
_Avoid_: Bug report, issue, result

**Evidence**:
Captured artifacts (screenshots, page state, request/response records) attached to an action or a Finding.
_Avoid_: Proof, logs

**Verdict**:
The outcome of a deterministic check on a Finding or step: PASS, FAIL, INCONCLUSIVE, or FLAKY. Never decided by an LLM.
_Avoid_: Judgment, score, evaluation

### Measurement

**Planted Defect**:
A known defect deliberately placed in our own Target and hidden from every Agent.
_Avoid_: Seeded bug, known bug

**Sealed Held-out Set**:
A frozen group of planted defects isolated from tuning and prompt development, whose contents are sealed and represented in the repository only by a cryptographic hash until final scoring.
_Avoid_: Test set, secret bugs, hidden benchmark

**Scoring Harness**:
An offline script that compares a finished Run's Findings against the Planted Defects (or Juice Shop's scoreboard). It is not part of the running system.
_Avoid_: Evaluation agent, evaluator

**Crawler**:
A non-LLM explorer that lists a Target's pages, forms, and links, producing the reference inventory for Coverage.
_Avoid_: Spider, scanner

**Coverage**:
The share of the Crawler's inventory that a Run actually exercised.
_Avoid_: Completeness, test coverage

---

## Architecture Decision Records

The domain model is governed by the Architecture Decision Records in `docs/adr/`:
- **ADR-0001:** Verdicts are deterministic; there is no runtime evaluation agent.
- **ADR-0002:** Provider spike results & profile configuration (OpenAI-compatible client, dev/bench profiles).
- **ADR-0003:** Verdict pipeline (FindingVerifier -> VerdictEngine -> Replayer -> finalize_verdict; offline scorer never writes verdicts).
- **ADR-0004:** Published results must be generated from scored run artifacts (`runs/<config>/<run_id>/score.json`); zero hardcoded literals; held-out re-seal.
- **ADR-0005:** Live dashboard and user-specified target execution incorporated into the roadmap with explicit runtime allowlist confirmation and route interception.
