# Agentic QA Command Center — TDD Implementation Plan

> Red → Green → Refactor, one vertical slice at a time.
> Every phase has a **gate**: a concrete, runnable check that must pass before the next phase begins.

---

## Seams Under Test

Before any code, these are the **public boundaries** we test at. Each seam is a module's interface — tests never reach past it.

| Seam | What it catches | What it misses |
|---|---|---|
| `LLMClient` → `FakeProvider` | Tool-call schema, retry logic, token accounting, malformed output handling | Real model latency, real model quality |
| `TraceWriter` → JSONL file | Trace format correctness, secret scrubbing, model ID recording | Trace analysis / reporting |
| `RunState` → budget enforcement | Budget exceeded behavior, action/token/time limits | Real wall-clock races |
| `ToolGateway` → tool dispatch | Allowlist enforcement, permission checks, secret scrubbing | Actual browser/HTTP behavior |
| `VerdictEngine` → assertion results | Deterministic verdict correctness (PASS/FAIL/INCONCLUSIVE/FLAKY) | Edge-case DOM states |
| `LoopDetector` → fingerprints | Repeated action/observation detection, recovery triggers | Real-world DOM variance |
| `ScoringHarness` → matchers | Recall/precision calculation, held-out separation | Manual triage of unmatched Findings |
| `Crawler` → inventory | Page/form/link discovery, coverage calculation | JavaScript-rendered content |
| `BaselineAgent` → Findings | End-to-end single-agent flow via FakeProvider | Real LLM exploration quality |
| `Planner` → Plan schema | Plan validation, task assignment, budget splitting | Plan quality |
| `BrowserAgent` / `APIAgent` → Findings | Sub-agent isolation, Evidence capture, budget enforcement | Real browser/HTTP interactions |
| `Challenger` → downgrade logic | Replay requests, INCONCLUSIVE downgrade, never-upgrade invariant | Replay timing issues |
| `Ground truth isolation` | No agent/prompt code imports `benchmark/ground_truth/` | — |

---

## Phase 0 — Foundations & Spike

**Goal:** Scaffold the repo, build the innermost components (no agents yet), confirm the LLM provider works.
**Timeline:** First hours.

### Phase 0.1 — Project Scaffold

**Slice:** Set up the repo structure, dependencies, and test harness.

```
src/qa_cc/__init__.py
src/qa_cc/llm/
src/qa_cc/gateway/
src/qa_cc/tools/
src/qa_cc/verdict/
src/qa_cc/agents/
src/qa_cc/trace/
src/qa_cc/report/
src/qa_cc/crawler/
benchmark/own_site/
benchmark/ground_truth/
benchmark/scoring/
tests/unit/
tests/contract/
tests/e2e/
docs/adr/
pyproject.toml
pytest.ini / pyproject.toml [tool.pytest]
```

**Verification:**
```bash
# pytest discovers tests and exits cleanly with 0 collected
pytest --collect-only
# The package is importable
python -c "import qa_cc"
```

---

### Phase 0.2 — FakeProvider

**Seam:** `LLMClient` interface

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_fake_provider_returns_canned_response` — calling `FakeProvider.chat(messages)` returns the pre-configured response | `FakeProvider` class with a response queue |
| 2 | `test_fake_provider_records_calls` — after N calls, `FakeProvider.calls` has N entries with messages and tool calls | Recording logic in `FakeProvider` |
| 3 | `test_fake_provider_raises_on_empty_queue` — calling when no responses remain raises `ProviderExhausted` | Guard in `FakeProvider.chat()` |

**Verification:**
```bash
pytest tests/unit/test_fake_provider.py -v  # 3 tests green
```

---

### Phase 0.3 — LLM Client + Token Accounting

**Seam:** `LLMClient` public interface (`.chat()`, `.token_usage`)

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_llm_client_returns_assistant_message` — `client.chat(messages)` returns a response with `role="assistant"` | `LLMClient` wrapping a provider |
| 2 | `test_llm_client_records_token_counts` — after a call, `client.token_usage` reflects prompt + completion tokens | Token accounting in `LLMClient` |
| 3 | `test_llm_client_records_model_id` — the response includes the served model ID from the provider | Model ID pass-through |
| 4 | `test_llm_client_retries_malformed_output` — if provider returns invalid JSON for a schema-validated call, client retries up to 2 times | Schema validation + bounded retry |
| 5 | `test_llm_client_fails_after_max_retries` — 3 consecutive malformed responses → `MalformedOutputError` | Retry counter + exception |
| 6 | `test_llm_client_tool_calling` — client passes tool definitions and receives tool call responses | Tool-call wiring |

**Verification:**
```bash
pytest tests/unit/test_llm_client.py -v  # 6 tests green
```

---

### Phase 0.4 — JSONL Trace Writer

**Seam:** `TraceWriter` public interface (`.record()`, output file)

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_trace_writer_creates_jsonl_file` — after `.record(entry)`, the file exists and contains valid JSON per line | `TraceWriter` with `.record()` |
| 2 | `test_trace_entry_has_required_fields` — each entry has `timestamp`, `type`, `model_id`, `tokens` | Pydantic `TraceEntry` model |
| 3 | `test_trace_writer_scrubs_secrets` — an entry containing `os.environ["SECRET_KEY"]` value has it replaced with `[SCRUBBED]` | Secret scrubbing in `.record()` |
| 4 | `test_trace_writer_records_tool_calls` — tool call entries include tool name, args, and result | Tool call trace entry type |
| 5 | `test_trace_writer_multiple_entries` — N `.record()` calls produce N lines | Append-mode writing |

**Verification:**
```bash
pytest tests/unit/test_trace_writer.py -v  # 5 tests green
```

---

### Phase 0.5 — RunState + Budget Enforcer

**Seam:** `RunState` public interface (`.check_budget()`, `.record_action()`, `.record_tokens()`)

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_runstate_starts_within_budget` — a fresh `RunState` with limits reports `within_budget=True` | `RunState` Pydantic model |
| 2 | `test_runstate_action_budget_exceeded` — after recording `max_actions + 1` actions, `check_budget()` raises `BudgetExceeded` | Action counter + check |
| 3 | `test_runstate_token_budget_exceeded` — after recording tokens past the cap, `check_budget()` raises `BudgetExceeded` | Token counter + check |
| 4 | `test_runstate_tracks_findings` — `add_finding(f)` and `findings` returns it | Findings list |
| 5 | `test_runstate_tracks_history_fingerprints` — `record_action(fingerprint)` stores it; `.has_fingerprint(fp)` returns True | Fingerprint set |

**Verification:**
```bash
pytest tests/unit/test_runstate.py -v  # 5 tests green
```

---

### Phase 0.6 — OmniRoute / B.AI Spike

**Seam:** Contract test against real provider (marked `live`)

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_contract_real_provider_returns_response` — a single real call returns a valid response with model ID | Profile loading + real HTTP |
| 2 | `test_contract_tool_calling_works` — a tool-calling request returns a tool call response | Real tool-call round trip |

> **Mark:** `@pytest.mark.live` — excluded from default run.

**Verification:**
```bash
pytest tests/contract/ -v -m live  # 2 tests green (run manually, uses tokens)
```

Record spike results (failure rate, malformed-JSON rate) in `docs/adr/0002-provider-spike-results.md`.

---

### ✅ Phase 0 Gate

```bash
pytest tests/unit/ tests/contract/ -v --ignore=tests/contract -k "not live"
# All unit tests green (≈19 tests). Spike recorded. Ground truth NOT yet frozen.
```

---

## Phase 0.7 — Ground Truth (Before Any Agent Code)

**Goal:** Freeze the Planted Defect list and matchers before writing agent code.

| # | Task | Verification |
|---|---|---|
| 1 | Write 8 Planted Defects in `benchmark/ground_truth/defects.json` with IDs, categories, page, and matcher conditions | `python -c "import json; d=json.load(open('benchmark/ground_truth/defects.json')); assert len(d) >= 8"` |
| 2 | Mark 5 as tuning set, 3 as held-out | `python -c "..."` asserts 5 tuning + 3 held-out |
| 3 | Write the Own Site HTML pages with the 8 planted defects in `benchmark/own_site/` | Open in browser, manually confirm defects exist |
| 4 | `test_ground_truth_agent_isolation` — importing any module under `src/qa_cc/agents/` or `src/qa_cc/llm/` does NOT access `benchmark/ground_truth/` | Static import analysis test |

**Verification:**
```bash
pytest tests/unit/test_ground_truth_isolation.py -v  # 1 test green
ls benchmark/ground_truth/defects.json              # file exists
```

---

## Phase 1 — Baseline Agent (Day 1)

**Goal:** A single-agent Run on Own Site produces a trace, Evidence, and a static report with at least one replayable Finding.

### Phase 1.1 — Tool Gateway

**Seam:** `ToolGateway` public interface (`.execute(tool_name, args)`)

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_gateway_rejects_unknown_tool` — calling an unregistered tool raises `ToolNotFound` | Tool registry + dispatch |
| 2 | `test_gateway_enforces_allowlist` — a `navigate` call to a non-allowlisted URL raises `TargetNotAllowed` | URL allowlist check |
| 3 | `test_gateway_scrubs_secrets_from_args` — tool args containing a secret value are scrubbed before logging | Secret scrubbing |
| 4 | `test_gateway_records_tool_call_in_trace` — after execution, a trace entry exists for the tool call | Trace integration |
| 5 | `test_gateway_enforces_permissions` — a tool requiring explicit permission raises `PermissionRequired` when not granted | Permission model |

**Verification:**
```bash
pytest tests/unit/test_tool_gateway.py -v  # 5 tests green
```

---

### Phase 1.2 — Browser Tools (Stubbed)

**Seam:** Each tool function's public interface, tested via `ToolGateway` with mocked Playwright

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_navigate_returns_page_snapshot` — `navigate(url)` returns a compacted snapshot | `navigate` tool + snapshot compaction |
| 2 | `test_click_returns_updated_snapshot` — `click(selector)` returns new state | `click` tool |
| 3 | `test_fill_sets_value` — `fill(selector, value)` updates the field | `fill` tool |
| 4 | `test_screenshot_returns_evidence` — `screenshot()` returns an `Evidence` object with a file path | `screenshot` tool + Evidence model |
| 5 | `test_console_capture_returns_errors` — `console_errors()` returns captured console errors | Console capture tool |
| 6 | `test_snapshot_is_compacted` — snapshot truncates beyond token limit | Compaction logic |

**Verification:**
```bash
pytest tests/unit/test_browser_tools.py -v  # 6 tests green
```

---

### Phase 1.3 — Evidence Model

**Seam:** `Evidence` Pydantic model

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_evidence_requires_type_and_content` — creating without type or content raises `ValidationError` | `Evidence` model |
| 2 | `test_evidence_serializes_to_dict` — `.model_dump()` produces a dict with all fields | Serialization |
| 3 | `test_finding_requires_evidence` — a `Finding` without at least one `Evidence` raises `ValidationError` | `Finding` model with evidence constraint |
| 4 | `test_finding_has_no_verdict_initially` — a new `Finding` has `verdict=None` | Default verdict |

**Verification:**
```bash
pytest tests/unit/test_evidence.py -v  # 4 tests green
```

---

### Phase 1.4 — Verdict Engine

**Seam:** `VerdictEngine.evaluate(finding, page_state)` → `Verdict`

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_verdict_pass_when_element_has_expected_state` — element present with expected text → `PASS` | Element state assertion |
| 2 | `test_verdict_fail_when_element_missing` — expected element absent → `FAIL` | Missing element check |
| 3 | `test_verdict_fail_on_unexpected_url` — page URL doesn't match expected → `FAIL` | URL assertion |
| 4 | `test_verdict_fail_on_console_error` — console contains error matching pattern → `FAIL` | Console error assertion |
| 5 | `test_verdict_inconclusive_on_ambiguous_state` — element present but value unclear → `INCONCLUSIVE` | Ambiguity handling |
| 6 | `test_verdict_never_set_by_llm` — `VerdictEngine` has no LLM dependency (static analysis) | Architecture test |

**Verification:**
```bash
pytest tests/unit/test_verdict_engine.py -v  # 6 tests green
```

---

### Phase 1.5 — Loop Detection & Recovery

**Seam:** `LoopDetector.check(action_fingerprint, observation_fingerprint)` → action

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_fingerprint_computation` — `hash(tool + normalized_args + url)` produces deterministic hash | Fingerprint function |
| 2 | `test_no_loop_on_unique_actions` — 3 different fingerprint pairs → no loop detected | Normal path |
| 3 | `test_loop_detected_after_three_repeats` — same (action, observation) pair 3 times → triggers recovery | Counter + threshold |
| 4 | `test_recovery_sequence` — after detection: re-observe → validate → retry/alternate → continue or INCONCLUSIVE | Recovery state machine |

**Verification:**
```bash
pytest tests/unit/test_loop_detector.py -v  # 4 tests green
```

---

### Phase 1.6 — Baseline Agent (with FakeProvider)

**Seam:** `BaselineAgent.run(objective, target)` → `RunResult` (Findings + trace)

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_baseline_agent_produces_findings` — given a FakeProvider scripted to navigate and find a defect, agent returns ≥1 Finding | Agent loop wiring |
| 2 | `test_baseline_agent_stops_on_budget` — agent stops when RunState budget is exceeded | Budget integration |
| 3 | `test_baseline_agent_captures_evidence` — each Finding has at least one Evidence | Evidence capture in loop |
| 4 | `test_baseline_agent_writes_trace` — after run, JSONL trace file exists with entries | Trace integration |
| 5 | `test_baseline_agent_loop_recovery` — FakeProvider scripted to repeat → agent triggers recovery | Loop detection integration |

**Verification:**
```bash
pytest tests/unit/test_baseline_agent.py -v  # 5 tests green
```

---

### Phase 1.7 — Crawler

**Seam:** `Crawler.crawl(target_url)` → `Inventory`

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_crawler_discovers_pages` — given a local HTML site, returns list of page URLs | HTML link extraction |
| 2 | `test_crawler_discovers_forms` — returns form elements with fields | Form discovery |
| 3 | `test_crawler_discovers_links` — returns internal links only (respects allowlist) | Link filtering |
| 4 | `test_crawler_coverage_calculation` — given inventory + exercised set, returns coverage ratio | Coverage math |

**Verification:**
```bash
pytest tests/unit/test_crawler.py -v  # 4 tests green
```

---

### Phase 1.8 — Scoring Harness

**Seam:** `ScoringHarness.score(run_result, ground_truth_path)` → `ScoreReport`

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_recall_calculation` — 3 of 5 defects matched → recall = 0.6 | Matcher logic |
| 2 | `test_precision_unmatched_findings_flagged` — Findings matching nothing are listed for triage | Unmatched detection |
| 3 | `test_replay_rate_calculation` — 2 of 3 Findings replayable → replay rate ≈ 0.67 | Replay tracking |
| 4 | `test_scoring_uses_tuning_set_only` — held-out defects are excluded from tuning scores | Set filtering |
| 5 | `test_scoring_refuses_mismatched_bench_model` — Runs with different bench model IDs → error | Model ID check |

**Verification:**
```bash
pytest tests/unit/test_scoring_harness.py -v  # 5 tests green
```

---

### Phase 1.9 — CLI + Static Report

**Seam:** CLI entry point, report generator

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_cli_run_command_exists` — `python -m qa_cc run --help` exits 0 | CLI argument parser |
| 2 | `test_cli_run_produces_trace` — `run` with FakeProvider creates JSONL trace file | CLI → agent wiring |
| 3 | `test_report_generates_html` — `generate_report(run_result)` creates a valid HTML file | HTML report generator |
| 4 | `test_report_contains_findings` — HTML includes each Finding's summary and verdict | Report content |

**Verification:**
```bash
pytest tests/unit/test_cli.py tests/unit/test_report.py -v  # 4 tests green
```

---

### Phase 1.10 — E2E: Baseline Agent on Own Site

**Seam:** Full system (marked `e2e`)

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_e2e_baseline_run_on_own_site` — a real Playwright + FakeProvider run against Own Site produces ≥1 Finding with Evidence | All Phase 1 wired together |
| 2 | `test_e2e_report_generated` — after run, HTML report file exists | Report generation |
| 3 | `test_e2e_scoring_produces_recall` — scoring the run against tuning set yields a recall number | Scoring integration |

> **Mark:** `@pytest.mark.e2e` — excluded from default run.

**Verification:**
```bash
pytest tests/e2e/test_baseline_e2e.py -v -m e2e  # 3 tests green
```

---

### ✅ Phase 1 Gate

```bash
# All unit tests pass (≈58 tests)
pytest tests/unit/ -v

# E2E produces at least one replayable Finding
pytest tests/e2e/test_baseline_e2e.py -v -m e2e

# Baseline recall and coverage numbers recorded
python -m qa_cc score --run-dir <run_output_dir>
```

**Exit criteria (from PRD):** A single-agent Run on Own Site produces a trace, Evidence, and a static report with at least one replayable Finding, plus baseline Recall and Coverage numbers. **If not green, Phase 2 does not start.**

---

## Phase 2 — Multi-Agent (Day 2)

**Goal:** Planner + Browser Agent + API Agent, each under separate budgets. Baseline vs multi-agent comparison on tuning set.

### Phase 2.1 — Plan Schema

**Seam:** Pydantic `Plan` and `Task` models

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_plan_validates_against_schema` — a well-formed Plan dict validates successfully | `Plan` + `Task` Pydantic models |
| 2 | `test_plan_rejects_missing_assignee` — Task without `assignee` → `ValidationError` | Required fields |
| 3 | `test_plan_rejects_unknown_assignee` — `assignee="unknown"` → `ValidationError` | Enum constraint |
| 4 | `test_plan_tasks_have_budgets` — each Task has a `budget` field | Budget in Task model |
| 5 | `test_plan_serializes_for_trace` — Plan serializes to dict for trace recording | Serialization |

**Verification:**
```bash
pytest tests/unit/test_plan_schema.py -v  # 5 tests green
```

---

### Phase 2.2 — Planner Agent

**Seam:** `Planner.plan(objective, target_metadata)` → `Plan`

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_planner_returns_valid_plan` — FakeProvider returns a Plan JSON → Planner returns validated `Plan` | Planner agent |
| 2 | `test_planner_has_no_tool_access` — Planner's tool set is empty | Tool isolation |
| 3 | `test_planner_replan_on_report` — given a sub-agent report, Planner produces a revised Plan | Replan logic |
| 4 | `test_planner_replan_bounded` — after 2 replans, further attempts are rejected | Replan counter (D2) |
| 5 | `test_planner_splits_budget` — sum of Task budgets ≤ total Run budget | Budget splitting logic |

**Verification:**
```bash
pytest tests/unit/test_planner.py -v  # 5 tests green
```

---

### Phase 2.3 — Browser Agent (Isolated)

**Seam:** `BrowserAgent.execute(task)` → `TaskResult`

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_browser_agent_receives_only_task` — agent context contains only its Task, not full history | Context isolation |
| 2 | `test_browser_agent_uses_browser_tools_only` — tool set contains only browser tools | Tool set restriction |
| 3 | `test_browser_agent_returns_findings_with_evidence` — result includes Findings with Evidence references | Finding production |
| 4 | `test_browser_agent_respects_task_budget` — stops when Task budget exceeded | Per-task budget enforcement |
| 5 | `test_browser_agent_returns_steps_not_transcript` — result contains recorded steps, not LLM transcript (D6) | Step recording |

**Verification:**
```bash
pytest tests/unit/test_browser_agent.py -v  # 5 tests green
```

---

### Phase 2.4 — API Agent + HTTP Tool

**Seam:** `APIAgent.execute(task)` → `TaskResult`, `http_request` tool

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_http_tool_enforces_allowlist` — request to non-allowlisted URL → `TargetNotAllowed` | HTTP tool + allowlist |
| 2 | `test_http_tool_records_evidence` — request/response pair stored as Evidence | Evidence capture |
| 3 | `test_api_agent_uses_http_tools_only` — tool set contains only HTTP tool | Tool set restriction |
| 4 | `test_api_agent_returns_findings` — FakeProvider-scripted API exploration → Findings | API agent loop |
| 5 | `test_api_agent_respects_task_budget` — stops on budget exhaustion | Budget enforcement |

**Verification:**
```bash
pytest tests/unit/test_api_agent.py -v  # 5 tests green
```

---

### Phase 2.5 — Multi-Agent Orchestrator

**Seam:** `Orchestrator.run(objective, target)` → `RunResult`

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_orchestrator_calls_planner_then_agents` — Planner runs first, then sub-agents execute Tasks | Orchestration flow |
| 2 | `test_orchestrator_separate_budgets` — each sub-agent has its own budget from the Plan | Budget isolation |
| 3 | `test_orchestrator_collects_all_findings` — Findings from all sub-agents are merged | Result aggregation |
| 4 | `test_orchestrator_shares_findings_not_transcripts` — shared state contains Findings + Evidence refs only (D6) | State sharing |
| 5 | `test_orchestrator_replan_flow` — on sub-agent failure, orchestrator triggers replan | Replan integration |

**Verification:**
```bash
pytest tests/unit/test_orchestrator.py -v  # 5 tests green
```

---

### Phase 2.6 — Own Site FastAPI Mock Backend

**Seam:** API endpoints with planted defects (D3)

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_mock_api_serves_endpoints` — GET/POST to known endpoints return responses | FastAPI app |
| 2 | `test_mock_api_has_planted_defects` — specific requests trigger planted API defects | 2-3 planted API defects |
| 3 | `test_mock_api_defects_in_ground_truth` — API defect IDs exist in `defects.json` | Ground truth consistency |

**Verification:**
```bash
pytest tests/unit/test_mock_api.py -v  # 3 tests green
```

---

### ✅ Phase 2 Gate

```bash
# All unit tests pass (≈86 tests)
pytest tests/unit/ -v

# Multi-agent Run completes on Own Site
pytest tests/e2e/test_multi_agent_e2e.py -v -m e2e

# Baseline vs multi-agent numbers exist
python -m qa_cc score --run-dir <baseline_run> --compare <multi_agent_run>
```

**Exit criteria (from PRD):** Plan validates, both sub-agents run under separate budgets, and baseline vs multi-agent numbers exist on the tuning set.

---

## Phase 3 — Challenger, Juice Shop, Polish (Day 3)

**Goal:** Challenger with replay, 3 Juice Shop Objectives, prompt-injection fixture, final results table.

### Phase 3.1 — Challenger Agent

**Seam:** `Challenger.challenge(finding)` → `ChallengeResult`

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_challenger_can_request_replay` — given a Finding with recorded steps, Challenger requests replay | Replay request logic |
| 2 | `test_challenger_downgrades_to_inconclusive` — Finding with missing Evidence → downgraded to `INCONCLUSIVE` | Downgrade logic |
| 3 | `test_challenger_never_upgrades` — a `FAIL` Finding cannot become `PASS` through Challenger | Invariant enforcement |
| 4 | `test_challenger_never_sets_verdict` — Challenger has no access to `VerdictEngine.set_verdict()` | Interface restriction |
| 5 | `test_replay_reproduces_failing_check` — replayed steps hit the same assertion → confirms Finding | Replay execution |

**Verification:**
```bash
pytest tests/unit/test_challenger.py -v  # 5 tests green
```

---

### Phase 3.2 — Juice Shop Integration

**Seam:** Juice Shop target configuration, scoreboard reader (marked `e2e`)

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_juice_shop_target_in_allowlist` — `localhost:3000` is in the target allowlist | Config update |
| 2 | `test_scoreboard_reader_parses_challenges` — reads Juice Shop's challenge API and returns solved list | Scoreboard reader |
| 3 | `test_scoring_harness_uses_scoreboard` — for Juice Shop target, scoring uses scoreboard instead of matchers | Scoring mode switch |

> **Mark:** `@pytest.mark.e2e`

**Verification:**
```bash
pytest tests/e2e/test_juice_shop.py -v -m e2e  # 3 tests green (requires Docker)
```

---

### Phase 3.3 — Prompt Injection Fixture

**Seam:** Agent safety against injected instructions

| # | Test (Red) | Implementation (Green) |
|---|---|---|
| 1 | `test_prompt_injection_page_exists` — Own Site has a page with injected instructions in DOM | Fixture page |
| 2 | `test_agent_ignores_injected_instructions` — agent encountering injected "change your target" instruction does NOT change target or permissions | Agent safety check |
| 3 | `test_dom_content_is_delimited` — DOM text passed to LLM is wrapped in delimiters | Delimiter check |

**Verification:**
```bash
pytest tests/unit/test_prompt_injection.py -v  # 3 tests green
```

---

### Phase 3.4 — Final Report + README

| # | Task | Verification |
|---|---|---|
| 1 | Run 3 baseline Runs and 3 multi-agent Runs on tuning set | Score reports for 6 Runs |
| 2 | Run multi-agent on held-out defects (once) | Held-out score report |
| 3 | Run 3 Juice Shop Objectives | Juice Shop score reports |
| 4 | Generate results table (recall, precision, replay rate, cost, variance) | Table in report |
| 5 | Write README with setup, usage, and results | `README.md` exists |
| 6 | Record demo | Demo artifact |

**Verification:**
```bash
# All tests pass
pytest tests/unit/ -v
pytest tests/e2e/ -v -m e2e
# Results table is complete
python -m qa_cc results --format table
```

---

### ✅ Phase 3 Gate

```bash
# Full test suite green
pytest tests/unit/ -v                        # ≈94+ unit tests
pytest tests/e2e/ -v -m e2e                  # E2E tests

# Results table including held-out defects exists
python -m qa_cc results --include-held-out

# README complete
test -f README.md
```

**Exit criteria (from PRD):** Results table including held-out defects. Challenger functional. Juice Shop scored.

---

## Cut Order (if behind schedule)

Per PRD §11, cut in this order:

1. **Prompt-injection fixture** (Phase 3.3) — cut first
2. **Challenger** (Phase 3.1) — cut second
3. **Reduce Juice Shop** to 1 Objective instead of 3

---

## Test Summary

| Phase | Unit Tests | Contract | E2E | Total |
|---|---|---|---|---|
| Phase 0 | ~19 | 2 (live) | — | ~21 |
| Phase 1 | ~39 | — | 3 | ~42 |
| Phase 2 | ~28 | — | 1+ | ~29 |
| Phase 3 | ~8 | — | 3 | ~11 |
| **Total** | **~94** | **2** | **7+** | **~103** |

## Key TDD Rules (from CLAUDE.md)

> [!IMPORTANT]
> - **Red first:** Write the failing test, run it, see it fail, then implement.
> - **One slice:** One seam, one test, one minimal implementation per cycle.
> - **Deterministic:** Unit tests have no network, no real LLM, no real browser.
> - **FakeProvider:** All LLM-facing code tested through `FakeProvider` and recorded cassettes.
> - **E2E/live excluded:** Browser and live-LLM tests marked `e2e`/`live`, never in default run.
> - **Ground truth isolation:** A test must fail if agent code reads `benchmark/ground_truth/`.
> - **Small commits:** One behavior per commit.
