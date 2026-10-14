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

### Agents

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

**Scoring Harness**:
An offline script that compares a finished Run's Findings against the Planted Defects (or Juice Shop's scoreboard). It is not part of the running system.
_Avoid_: Evaluation agent, evaluator

**Crawler**:
A non-LLM explorer that lists a Target's pages, forms, and links, producing the reference inventory for Coverage.
_Avoid_: Spider, scanner

**Coverage**:
The share of the Crawler's inventory that a Run actually exercised.
_Avoid_: Completeness, test coverage
