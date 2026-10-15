# Agentic QA Command Center (`qa_cc`)

> **Autonomous web application testing and defect discovery powered by multi-agent LLM exploration and deterministic verdict enforcement.**

`qa_cc` is an agentic QA framework designed to autonomously explore web applications, execute exploratory and regression testing, and capture cryptographically traced defect findings backed by concrete DOM, network, and console evidence.

---

## Table of Contents

- [Core Principles](#core-principles)
- [Architecture & Agent Ecosystem](#architecture--agent-ecosystem)
- [Empirical Evidence & Discovered Defects](#empirical-evidence--discovered-defects)
- [Installation & Quickstart](#installation--quickstart)
- [Usage Guide](#usage-guide)
  - [1. Single-Agent Autonomous Exploration](#1-single-agent-autonomous-exploration)
  - [2. Multi-Agent Orchestrated Exploration](#2-multi-agent-orchestrated-exploration)
  - [3. Deterministic Mock Mode (Zero-Token Testing)](#3-deterministic-mock-mode-zero-token-testing)
  - [4. Benchmark Scoring Against Ground Truth](#4-benchmark-scoring-against-ground-truth)
- [Action Budget & Tuning Guidelines](#action-budget--tuning-guidelines)
- [Testing & Quality Assurance](#testing--quality-assurance)
- [Project Structure](#project-structure)

---

## Core Principles

1. **Deterministic Verdicts (No LLM Judges):**
   The LLM agent proposes findings and gathers evidence, but the model **never** decides its own pass/fail verdicts. All verdicts are strictly determined by the deterministic `VerdictEngine` or through verifiable assertion rules.
2. **Tool Gateway Security & Compliance:**
   All browser and HTTP actions must route through the `ToolGateway`. The gateway enforces a strict hostname allowlist, scrubs environment secrets from traces and logs, and maintains an append-only JSONL audit trail.
3. **Context Isolation (PRD Rule D6):**
   Sub-agents (Browser and API) execute their assigned tasks in isolated context windows without prior conversation history bloat. Inter-agent communication is restricted to structured findings and evidence references.
4. **Loop Detection & Recovery:**
   An action-observation fingerprinting engine detects repetitive or oscillating agent behavior (e.g., repeating form submits or cyclic page navigation) and forces recovery procedures (`RE_OBSERVE` → `TRY_ALTERNATE` → `TERMINATE`).

---

## Architecture & Agent Ecosystem

```
                      ┌────────────────────────────────────────┐
                      │              CLI (cli.py)              │
                      │  run [--multi-agent] [--mock]          │
                      │  score --run-dir DIR [--compare DIR2]  │
                      └──────────────────┬─────────────────────┘
                                         │
                 ┌───────────────────────┴──────────────────────┐
                 │                                              │
                 ▼ (Single Agent Mode)                          ▼ (Multi-Agent Mode)
      ┌─────────────────────┐                      ┌────────────────────────────┐
      │    BaselineAgent    │                      │        Orchestrator        │
      └──────────┬──────────┘                      └──────────────┬─────────────┘
                 │                                                │
                 │                         ┌──────────────────────┼──────────────────────┐
                 │                         ▼                      ▼                      ▼
                 │                  ┌─────────────┐       ┌──────────────┐       ┌──────────────┐
                 │                  │   Planner   │       │ BrowserAgent │       │   APIAgent   │
                 │                  │ (no tools)  │       │(browser tools│       │ (HTTP tool)  │
                 │                  └─────────────┘       └──────┬───────┘       └──────┬───────┘
                 │                                               │                      │
                 └───────────────────────────────┬───────────────┴──────────────────────┘
                                                 │
                                       ┌─────────▼─────────┐
                                       │    ToolGateway    │
                                       │ (allowlist, scrub,│
                                       │   permissions)    │
                                       └─────────┬─────────┘
                                                 │
                         ┌───────────────────────┴───────────────────────┐
                         ▼                                               ▼
               ┌───────────────────┐                           ┌───────────────────┐
               │   BrowserTools    │                           │     HttpTool      │
               │ (Playwright / DOM)│                           │(FastAPI / REST)   │
               └───────────────────┘                           └───────────────────┘

   Evaluation & Verification:
   ┌──────────────┐    ┌───────────────┐    ┌─────────────────┐
   │ VerdictEngine│    │ ScoringHarness│    │ ReportGenerator │
   │(deterministic│    │ (recall vs    │    │ (dark-mode HTML │
   │  assertions) │    │  ground truth)│    │  with evidence) │
   └──────────────┘    └───────────────┘    └─────────────────┘
```

### The Agents & Components

| Component | Role | Mechanics & Constraints |
|---|---|---|
| **`Planner`** | High-level decomposition | Takes natural language objectives and creates an execution `Plan` consisting of typed tasks (`BROWSER` or `API`). Has **zero tool access**. Dynamically splits action and token budgets. Supports bounded replanning (max 2 replans). |
| **`BrowserAgent`** | UI & DOM exploration | Drives headless Chromium via Playwright. Employs compact DOM snapshots, interaction controls (`click`, `fill`, `navigate`), screenshot capture, and browser console listener. Operates in an isolated prompt context. |
| **`APIAgent`** | Network & API validation | Executes targeted REST requests (`GET`, `POST`, `PUT`, `DELETE`). Validates status codes, payload shapes, and backend defect signatures. |
| **`BaselineAgent`** | Single-agent baseline | Unified exploratory loop for end-to-end testing without planner separation. Serves as our benchmark baseline. |
| **`ToolGateway`** | Security enforcement | Verifies target URLs against allowlists, scrubs sensitive strings/keys, assigns task IDs, and records execution traces. |
| **`VerdictEngine`** | Automated verification | Evaluates rules (`element_exists`, `no_console_errors`, `element_contains_text`, `url_equals`) deterministically without LLM calls. |
| **`LoopDetector`** | Anti-hallucination guard | Tracks SHA-256 fingerprints of action-observation pairs. Triggers recovery after 3 consecutive identical states. |
| **`ScoringHarness`** | Benchmark evaluation | Computes recall and replay rate against frozen ground truth defect datasets (`defects.json`). |
| **`ReportGenerator`** | Executive reporting | Generates self-contained, responsive dark-theme HTML reports displaying KPIs, finding cards, and expandable DOM/screenshot evidence. |

---

## Empirical Evidence & Discovered Defects

During live testing against an e-commerce food delivery application ("The Noshery" running on `http://127.0.0.1:5500`), `qa_cc` autonomously discovered multiple critical defects:

### 1. Defect `F-1`: Unbounded Negative Cart Quantities
* **Category:** State Logic / Business Rule Violation
* **Discovered By:** `BrowserAgent` (12 actions)
* **Description:** Decrementing cart items below `1` allows item quantities to become `0`, `-1`, `-2`, etc. This yields negative line totals (`$-4.99`, `$-9.98`), effectively subtracting cost from the order.
* **Evidence (DOM Snapshot):**
  ```html
  <!-- State after clicking '-' button 4 times on Garlic Bread: -->
  <div class="cart-row">
    <h3>Garlic Bread</h3>
    <span class="price">$4.99 each</span>
    <div class="qty">
      <button class="dec" data-id="garlic-bread">−</button>
      <span>-2</span>
      <button class="inc" data-id="garlic-bread">+</button>
    </div>
    <div class="line-total">$-9.98</div>
  </div>
  ```

### 2. Defect `F-2`: Stale Cart Summary & Total Desynchronization
* **Category:** Client-Side State Desynchronization
* **Discovered By:** `BrowserAgent` (12 actions)
* **Description:** When adjusting item quantities or removing items, the item row re-renders, but `#cart-total`, `#cart-headline`, and `#cart-badge` remain frozen from the initial page load (`$28.73`, `4 items`). Furthermore, `checkout.html` reads the stale cached total from `localStorage`, causing checkout invoices to mismatch the actual cart contents.
* **Evidence (DOM Snapshot):**
  ```html
  <!-- Sum of items is $8.77, yet summary displays stale load total: -->
  <span id="cart-total" class="price">$28.73</span>
  <span id="cart-badge" class="badge">4</span>
  <p id="cart-headline" class="hint">You have 4 items in your cart</p>
  ```

### 3. Defect `F-3`: Case-Sensitive Catalog Search
* **Category:** Functional Search Defect
* **Discovered By:** `BaselineAgent` (11 actions)
* **Description:** Searching for `"pizza"` (lowercase) rendered `<p class="empty">No dishes match</p>`, while searching for `"Pizza"` (capitalized) correctly matched *Margherita Pizza* and *Pepperoni Pizza*. The search algorithm omitted `.toLowerCase()`.

---

## Installation & Quickstart

### Prerequisites
- Python 3.11+
- Playwright Chromium browser binaries

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/Fairoos-palakkal/Automation-agent.git
cd Automation-agent

# 2. Create and activate a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies in editable mode
pip install -e ".[dev]"

# 4. Install Playwright browser engines
playwright install chromium
```

### Configuration (`.env`)

Create a `.env` file in the project root:

```ini
# Primary LLM Endpoint (B.AI / OmniRoute / OpenAI compatible)
BAI_API_KEY=your_api_key_here
BAI_BASE_URL=https://api.omniroute.ai/v1
BAI_MODEL_ID=qwen/qwen-2.5-72b-instruct

# Optional: Secondary model for challenger / multi-agent evaluation
BAI_SECONDARY_MODEL_ID=google/gemini-2.5-flash
```

---

## Usage Guide

### 1. Single-Agent Autonomous Exploration

Run the baseline agent against any local or remote web target:

```bash
python -m qa_cc run \
  --target "http://127.0.0.1:5500" \
  --objective "Explore the menu and cart: test item quantities, boundary limits, and checkout form validation" \
  --output-dir "./run_output" \
  --max-actions 25
```

Outputs generated in `./run_output`:
- `report.html`: Interactive dark-mode dashboard displaying findings, severity badges, and DOM traces.
- `findings.json`: Structured list of findings with complete evidence attachments.
- `trace.jsonl`: Cryptographic action-observation audit log with redacted secrets.

### 2. Multi-Agent Orchestrated Exploration

Run with the Planner + BrowserAgent + APIAgent architecture:

```bash
python -m qa_cc run \
  --target "http://127.0.0.1:5500" \
  --objective "Validate cart state consistency, checkout order placement, and API backend endpoints" \
  --output-dir "./multi_agent_run" \
  --multi-agent \
  --max-actions 35
```

### 3. Deterministic Mock Mode (Zero-Token Testing)

You can run complete end-to-end exploration pipelines without consuming live LLM tokens using the built-in deterministic `FakeProvider`:

```bash
python -m qa_cc run \
  --target "http://localhost:3000" \
  --objective "Verify cart checkout and contact form" \
  --output-dir "./mock_run" \
  --mock
```

### 4. Benchmark Scoring Against Ground Truth

Score an agent run against frozen ground truth defects:

```bash
python -m qa_cc score \
  --run-dir ./run_output \
  --ground-truth benchmark/ground_truth/defects.json
```

Compare baseline vs. multi-agent runs side-by-side:

```bash
python -m qa_cc score \
  --run-dir ./run_output \
  --compare ./multi_agent_run
```

---

## Action Budget & Tuning Guidelines

Because each agent interaction appends DOM snapshots and tool records to the context window, optimizing action budgets prevents context drift and unnecessary token expenditure:

| Scope | Recommended Actions | Notes |
|---|---|---|
| **Targeted Boundary Test** | `15 – 20` | Ideal for individual workflows (e.g., negative cart quantities, promo codes, form errors). High recall, fastest execution. |
| **Full Site Exploration (Single Agent)** | `25 – 35` | Suitable for 3–5 pages. Reaches the sweet spot before context saturation occurs. |
| **Multi-Agent Orchestrator** | `30 – 45` | Total budget divided by the Planner across sub-agents. Because sub-agents run in isolated context windows, larger budgets remain stable. |

---

## Testing & Quality Assurance

The codebase adheres strictly to test-driven development (TDD) with 100% deterministic unit tests:

```bash
# Run all unit tests (fast, no external network, zero LLM tokens)
pytest tests/unit/ -v

# Run End-to-End browser tests (Playwright)
pytest tests/e2e/ -v -m e2e

# Run Live Provider Contract tests (requires .env credentials)
pytest tests/contract/ -v -m live
```

---

## Project Structure

```
Automation-agent/
├── benchmark/
│   ├── ground_truth/       # Frozen reference defects (defects.json)
│   ├── own_site/           # Built-in reference web app with planted bugs
│   └── scoring/            # Recall & replay calculation harness
├── docs/                   # Architecture Decision Records (ADRs)
├── src/qa_cc/
│   ├── agents/             # Planner, BrowserAgent, APIAgent, Baseline, LoopDetector
│   ├── crawler/            # Non-LLM link and form discovery crawler
│   ├── gateway/            # Security gateway, allowlist & secret scrubber
│   ├── llm/                # OpenAI-compatible provider & FakeProvider
│   ├── report/             # Dark-theme HTML report generator
│   ├── tools/              # BrowserTools (Playwright), HttpTool, MockAPI
│   ├── trace/              # RunState, TraceWriter (append-only JSONL)
│   ├── verdict/            # VerdictEngine (deterministic assertions)
│   └── cli.py              # CLI entry point (qa_cc run, qa_cc score)
├── tests/
│   ├── unit/               # 100 fast deterministic unit tests
│   ├── contract/           # Live provider contract tests
│   └── e2e/                # End-to-end browser & multi-agent tests
├── pyproject.toml          # Project configuration & dependencies
└── README.md               # Project documentation & evidence showcase
```

---

## License

MIT
