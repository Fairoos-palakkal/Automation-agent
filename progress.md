# Agentic QA Command Center — Progress Report

> **Last Updated:** 2026-10-14  
> **Completed Phases:** Phase 0, Phase 1  
> **Next Phase:** Phase 2 (Multi-Agent Architecture)  
> **Test Status:** 70 unit tests passing, E2E passing, contract tests passing

---

## Phase 0 — Scaffolding, Seams & Ground Truth (Complete ✅)

Phase 0 established the project skeleton, the fake-first testing infrastructure, and the frozen benchmark defects.

### 0.1 — Project Scaffold

| Item | File | Purpose |
|---|---|---|
| Package config | [`pyproject.toml`](file:///Users/fairoospalakkal/Desktop/Automation-agent/pyproject.toml) | Python 3.11+, Pydantic, Playwright, pytest with `e2e`/`live` markers |
| CLI entry point | [`src/qa_cc/__main__.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/__main__.py) | `python -m qa_cc` invocation |
| Project rules | [`CLAUDE.md`](file:///Users/fairoospalakkal/Desktop/Automation-agent/CLAUDE.md) | 8 non-negotiable rules including "LLM never decides Verdict" |
| Environment | [`.env.example`](file:///Users/fairoospalakkal/Desktop/Automation-agent/.env.example) | Template for B.AI / OmniRoute credentials |
| Secrets | [`.env`](file:///Users/fairoospalakkal/Desktop/Automation-agent/.env) | Live B.AI API key (gitignored) |
| Git safety | [`.gitignore`](file:///Users/fairoospalakkal/Desktop/Automation-agent/.gitignore) | Ignores `.env`, `.venv`, `run_output`, caches |

### 0.2 — FakeProvider (Canned-Response Queue)

| File | What it does |
|---|---|
| [`src/qa_cc/llm/fake_provider.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/llm/fake_provider.py) | Deterministic response queue with call recording. Raises `ProviderExhausted` when empty. |
| [`tests/unit/test_fake_provider.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_fake_provider.py) | 4 tests: canned response, call recording, exhaustion, tool kwargs |

### 0.3 — LLMClient (Token Accounting + Schema Validation)

| File | What it does |
|---|---|
| [`src/qa_cc/llm/client.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/llm/client.py) | Wraps any provider. Tracks `prompt_tokens`, `completion_tokens`, `total_tokens`. `chat_with_schema()` retries up to 2 times on malformed output. |
| [`tests/unit/test_llm_client.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_llm_client.py) | 7 tests: response shape, token accumulation, model ID tracking, retry logic, tool calling pass-through |

### 0.4 — TraceWriter (Append-Mode JSONL + Secret Scrubbing)

| File | What it does |
|---|---|
| [`src/qa_cc/trace/writer.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/trace/writer.py) | Writes timestamped entries to JSONL. Recursively scrubs secret env var values to `[SCRUBBED]`. |
| [`tests/unit/test_trace_writer.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_trace_writer.py) | 5 tests: file creation, required fields, secret scrubbing, tool call entries, multi-entry append |

### 0.5 — RunState (Budget Enforcement)

| File | What it does |
|---|---|
| [`src/qa_cc/trace/run_state.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/trace/run_state.py) | Mutable per-run state: action count, token count, findings list, fingerprint history. `check_budget()` raises `BudgetExceeded`. |
| [`tests/unit/test_runstate.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_runstate.py) | 7 tests: initial state, action budget exceeded, token budget exceeded, findings tracking, fingerprint history |

### 0.6 — OpenAI-Compatible Provider + Contract Tests

| File | What it does |
|---|---|
| [`src/qa_cc/llm/openai_provider.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/llm/openai_provider.py) | Wraps the `openai` SDK for any compatible endpoint. Pins model ID, strips kwargs. |
| [`tests/contract/test_provider_contract.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/contract/test_provider_contract.py) | 2 live tests (marked `@pytest.mark.live`): basic response shape, tool calling. Loads `.env` for credentials. |
| [`docs/adr/0002-provider-spike-results.md`](file:///Users/fairoospalakkal/Desktop/Automation-agent/docs/adr/0002-provider-spike-results.md) | Records spike invariants: OpenAI compat, tool calling, token usage, retry behavior |

### 0.7 — Ground Truth Defects + Benchmark Site

| File | What it does |
|---|---|
| [`benchmark/ground_truth/defects.json`](file:///Users/fairoospalakkal/Desktop/Automation-agent/benchmark/ground_truth/defects.json) | 8 planted defects: 5 tuning, 3 held-out. Each has `id`, `category`, `page`, `matcher`. |
| [`benchmark/own_site/*.html`](file:///Users/fairoospalakkal/Desktop/Automation-agent/benchmark/own_site/index.html) | 6 static HTML pages (index, catalog, cart, checkout, contact, account) with intentional bugs |
| [`tests/unit/test_ground_truth_isolation.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_ground_truth_isolation.py) | 3 tests: defect count/partitioning, page existence, **AST analysis proving agent code never references ground truth** |
| [`docs/adr/0001-deterministic-verdicts-no-evaluation-agent.md`](file:///Users/fairoospalakkal/Desktop/Automation-agent/docs/adr/0001-deterministic-verdicts-no-evaluation-agent.md) | Architecture decision: no LLM judge, verdicts are deterministic only |

**Planted Defects Summary:**

| ID | Name | Category | Set | Page |
|---|---|---|---|---|
| DEFECT-001 | Missing email validation | form_validation | tuning | /contact.html |
| DEFECT-002 | Broken navigation link | broken_navigation | tuning | /index.html |
| DEFECT-003 | Unhandled TypeError on catalog filter | console_error | tuning | /catalog.html |
| DEFECT-004 | Cart quantity allows negative values | state_logic | tuning | /cart.html |
| DEFECT-005 | Missing accessible name on subscribe button | accessibility | tuning | /index.html |
| DEFECT-006 | Modal overlay intercepts checkout button | visual_layout | held_out | /checkout.html |
| DEFECT-007 | Repeated promo code negative balance | state_logic | held_out | /cart.html |
| DEFECT-008 | Logout button unhandled promise rejection | broken_navigation | held_out | /account.html |

---

## Phase 1 — Single-Agent Loop (Complete ✅)

Phase 1 built the full single-agent exploration pipeline from tool gateway to HTML report generation.

### 1.1 — ToolGateway (Enforcement Layer)

| File | What it does |
|---|---|
| [`src/qa_cc/gateway/gateway.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/gateway/gateway.py) | Central tool dispatch. Enforces: tool registry, URL allowlist, secret scrubbing, permission gating, trace recording. |
| [`tests/unit/test_tool_gateway.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_tool_gateway.py) | 5 tests: unknown tool rejection, allowlist enforcement, secret scrubbing in traces, trace recording, permission gating |

### 1.2 — BrowserTools + PlaywrightPageDriver

| File | What it does |
|---|---|
| [`src/qa_cc/tools/browser.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/tools/browser.py) | `navigate`, `click`, `fill`, `screenshot`, `console_errors`, `snapshot`. Includes `compact_snapshot()` that strips `<script>`, `<style>`, comments, and truncates. |
| [`src/qa_cc/tools/playwright_driver.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/tools/playwright_driver.py) | Adapts Playwright `Page` to the driver interface. Captures console messages. |
| [`tests/unit/test_browser_tools.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_browser_tools.py) | 6 tests with `FakePageDriver`: navigate, click, fill, screenshot evidence, console capture, snapshot compaction |

### 1.3 — Evidence & Finding Models (Pydantic)

| File | What it does |
|---|---|
| [`src/qa_cc/verdict/evidence.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/verdict/evidence.py) | `Evidence`, `Verdict`, `Finding` Pydantic models. `EvidenceType` enum (screenshot, console_log, dom_snapshot, network_request, assertion_check). `VerdictType` enum (PASS, FAIL, INCONCLUSIVE, FLAKY). Finding validates ≥1 evidence. |
| [`tests/unit/test_evidence.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_evidence.py) | 4 tests: required fields, serialization, evidence requirement on Finding, initial verdict=None |

### 1.4 — VerdictEngine (Deterministic Assertions)

| File | What it does |
|---|---|
| [`src/qa_cc/verdict/engine.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/verdict/engine.py) | Evaluates `AssertionRule` against page state. Rules: `url_equals`, `no_console_errors`, `element_exists`, `element_contains_text`. Returns `INCONCLUSIVE` on ambiguous state. **Zero LLM dependencies** (enforced by AST test). |
| [`tests/unit/test_verdict_engine.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_verdict_engine.py) | 6 tests: element PASS, element FAIL, URL mismatch, console error FAIL, ambiguous INCONCLUSIVE, AST invariant check |

### 1.5 — LoopDetector (Action-Observation Cycle Breaking)

| File | What it does |
|---|---|
| [`src/qa_cc/agents/loop_detector.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/agents/loop_detector.py) | Fingerprints action+observation pairs. After 3 consecutive repeats: RE_OBSERVE → TRY_ALTERNATE → TERMINATE_INCONCLUSIVE. |
| [`tests/unit/test_loop_detector.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_loop_detector.py) | 4 tests: deterministic fingerprints, no false loops, threshold triggering, full recovery sequence |

### 1.6 — BaselineAgent (Multi-Turn Exploration Loop)

| File | What it does |
|---|---|
| [`src/qa_cc/agents/baseline.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/agents/baseline.py) | Autonomous agent loop: system prompt → LLM call → parse tool calls → execute via gateway → record → repeat. Handles `report_finding`, `finish`, budget enforcement, loop recovery. Emits `RunResult`. Includes 6 `DEFAULT_TOOLS` schemas. |
| [`tests/unit/test_baseline_agent.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_baseline_agent.py) | 5 tests: finding production, budget termination, evidence capture, trace writing, loop recovery |

### 1.7 — Crawler (Non-LLM Page Discovery)

| File | What it does |
|---|---|
| [`src/qa_cc/crawler/crawler.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/crawler/crawler.py) | Breadth-first page crawler. Extracts links and forms via regex. Respects allowlist. `Inventory.calculate_coverage()` computes exercised-vs-total ratio. |
| [`tests/unit/test_crawler.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_crawler.py) | 4 tests with mock site map: page discovery, form extraction, link filtering (rejects external), coverage calculation |

### 1.8 — ScoringHarness (Offline Recall Measurement)

| File | What it does |
|---|---|
| [`benchmark/scoring/harness.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/benchmark/scoring/harness.py) | Matches findings to planted defects by keyword/description/URL overlap. Calculates recall, replay rate. Rejects mismatched bench models. |
| [`tests/unit/test_scoring_harness.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_scoring_harness.py) | 5 tests: recall calculation, unmatched flagging, replay rate, tuning-only filtering, model mismatch rejection |

### 1.9 — CLI + Report Generator

| File | What it does |
|---|---|
| [`src/qa_cc/cli.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/cli.py) | `run` subcommand (mock or live mode with Playwright), `score` subcommand. Auto-loads `.env`, exports `findings.json`. |
| [`src/qa_cc/report/generator.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/src/qa_cc/report/generator.py) | Generates styled dark-theme HTML report with stats grid, finding cards, evidence items, verdict badges. |
| [`tests/unit/test_cli.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_cli.py) | 3 tests: help exits 0, run help shows flags, mock run produces trace + report |
| [`tests/unit/test_report.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/unit/test_report.py) | 2 tests: HTML generation, findings/evidence/verdict in output |

### 1.10 — End-to-End Test

| File | What it does |
|---|---|
| [`tests/e2e/test_baseline_e2e.py`](file:///Users/fairoospalakkal/Desktop/Automation-agent/tests/e2e/test_baseline_e2e.py) | Full pipeline: starts HTTP server for `benchmark/own_site`, launches Playwright, runs scripted BaselineAgent, verifies findings, generates report, scores against ground truth (expects DEFECT-003 matched). Marked `@pytest.mark.e2e`. |

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│                      CLI (cli.py)                       │
│  run --target URL --objective TEXT [--mock] [--max-N]   │
│  score --run-dir DIR --ground-truth FILE                │
└───────────────────────┬─────────────────────────────────┘
                        │
         ┌──────────────▼──────────────┐
         │      BaselineAgent          │
         │  (multi-turn LLM loop)      │
         │  ┌────────────────────────┐ │
         │  │ LoopDetector           │ │
         │  │ (cycle-break FSM)      │ │
         │  └────────────────────────┘ │
         └──────┬─────────────┬────────┘
                │             │
    ┌───────────▼──┐   ┌──────▼──────┐
    │  LLMClient   │   │ ToolGateway │
    │  (token acct)│   │ (allowlist, │
    │              │   │  scrub,     │
    │  FakeProvider│   │  trace)     │
    │  OpenAIComp. │   └──────┬──────┘
    └──────────────┘          │
                     ┌────────▼────────┐
                     │  BrowserTools   │
                     │  (navigate,     │
                     │   click, fill,  │
                     │   screenshot)   │
                     │                 │
                     │  Playwright     │
                     │  PageDriver     │
                     └─────────────────┘

  Offline:
  ┌──────────────┐    ┌───────────────┐
  │ VerdictEngine│    │ ScoringHarness│
  │ (deterministic│   │ (recall vs    │
  │  assertions) │    │  ground truth)│
  └──────────────┘    └───────────────┘
```

---

## Test Coverage Summary

| Category | Tests | Status |
|---|---|---|
| Unit tests | 70 | ✅ All passing |
| E2E (Playwright) | 1 | ✅ Passing |
| Contract (B.AI live) | 2 | ✅ Passing |
| **Total** | **73** | ✅ |

---

## How to Run

```bash
# Activate environment
source .venv/bin/activate

# Unit tests (fast, no network)
pytest tests/unit/ -v

# E2E test (requires Playwright browsers)
pytest tests/e2e/ -v -m e2e

# Contract tests (consumes real tokens)
pytest tests/contract/ -v -m live

# Run agent in mock mode
python -m qa_cc run --target http://localhost:3000 --objective "Sanity test" --mock

# Run agent against live site
python -m qa_cc run --target http://127.0.0.1:5500/index.html --objective "Explore and find bugs" --max-actions 10

# Score findings
python -m qa_cc score --run-dir ./run_output --ground-truth benchmark/ground_truth/defects.json
```

---

## Pre-Phase 2 Checklist

- [x] `pytest tests/unit/ -v` → 70 passed
- [x] `.env` has valid B.AI API key
- [x] `pytest tests/contract/ -v -m live` → 2 passed
- [x] `pytest tests/e2e/ -v -m e2e` → 1 passed
- [x] `defects.json` has 5 tuning + 3 held-out defects
- [x] All 6 benchmark HTML pages exist with planted bugs
- [x] Agent code never imports `ground_truth` (AST-verified)
- [x] VerdictEngine never imports `llm` (AST-verified)
- [ ] **Phase 2:** Multi-Agent Architecture (Planner + Browser Agent + API Agent)
