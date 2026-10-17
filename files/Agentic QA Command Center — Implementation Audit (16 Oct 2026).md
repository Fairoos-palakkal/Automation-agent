# Agentic QA Command Center — Implementation Audit

*Audit of `Automation-agent copy.zip` against `files/PRD.md`, `tdd_implementation_plan.md`, `CONTEXT.md`, ADR-0001/0002 and `CLAUDE.md` · 16 Oct 2026*

## 0. Scope, method and limits

**Inspected:** every file under `src/qa_cc` (agents, gateway, llm, tools, verdict, trace, report, crawler, cli), `benchmark/` (ground truth, scoring, own\_site), all 35 test files, ADRs, README, progress.md, PROJECT\_PORTFOLIO.md, and the five committed run directories.

**Executed (evidence labels used below):**

- **\[V\] Verified by execution.** Unit + contract suite: **114 passed, 2 live tests deselected**. E2E: 3 passed (Juice Shop tests, all mock-based), 2 failed only because Chromium could not be downloaded in my sandbox. Fifteen small proof-of-concept scripts reproduced the defects tagged \[V\].
- **\[C\] Verified by reading the code** (file and line given), not executed.
- **\[S\] Suspected or inferred.** Not proven; stated as such.

**Not available / not verified:** `.git` history, `.env`, `.gitignore`, `.agents/` (none are in the zip); a live LLM; Docker Juice Shop; Playwright browser runs (Own Site e2e and multi-agent e2e are therefore **Not Verifiable** here); the PRD PDF was not diffed against `files/PRD.md`. Nothing in the codebase was modified.

## 1. Executive summary (Deliverable 1)

**Overall status.** The scaffolding is genuinely good: clean seams, FakeProvider-first testing, Pydantic models, ADRs, an AST test for ground-truth isolation, 114 green unit tests. Phases 0–3 exist as code. But the project **does not do what its README and portfolio say it does**, and several non-negotiable rules in `CLAUDE.md` are not enforced on the real run path.

**The five things that matter most**

1. **The benchmark table is hard-coded, not measured (F-01).** `qa-cc results` prints literals and never reads a run. I ran it in an empty directory and got the full 80% / 66.7% table. README and PROJECT\_PORTFOLIO publish those numbers. The only real multi-agent trace used **981,598 tokens**; the table says **26,800–37,100**. This is the single biggest risk to the project's credibility.
2. **The core promise (deterministic verdicts, evidence-first, replay) is not wired (F-02, F-03).** `VerdictEngine.evaluate` is never called on the run path, `Challenger` and `Crawler` are never called by the CLI, baseline findings carry fingerprint-only steps that cannot be replayed, and the only verdicts found in committed artifacts were stamped by the scoring harness using keyword matching.
3. **Safety rules fail in practice (F-04, F-05, F-08, F-09, F-10).** The allowlist is a substring check (bypassed by `http://localhost.evil.com`), HTTP redirects and in-page clicks escape it, secret scrubbing is never switched on, the untrusted-DOM delimiter can be closed by the page, and the HTML report renders evidence unescaped.
4. **Black-box testing is compromised (F-07).** Agent prompts hard-code Juice Shop selectors, endpoints, the SQLi payload, and Noshery bug classes. Recall on those targets proves the prompt, not the agent.
5. **Multi-agent control flow is partly dead code (F-11, F-13).** Real agents can never return `failed`, so replanning is unreachable; the run-level budget is never counted; `prior_findings` is never read; context grows quadratically (46K-token prompts by turn 40).

**Most important next steps (in order):** delete or compute the benchmark numbers → fix the allowlist and report escaping → wire VerdictEngine + replayable steps + Challenger into `run` → strip target knowledge from prompts → fix orchestrator budget/replan → run real, scored, repeated runs and publish only what the tool generates.

**What is solid and should be kept:** module seams (`LLMClient`, `ToolGateway`, `RunState`, `TraceWriter`), `FakeProvider`, the Evidence/Finding models, per-task budgets, ADR-0001, the ground-truth AST test, defect list and Own Site pages, the Juice Shop scoreboard reader concept.

## 2. Requirements Traceability Matrix (Deliverable 2)

| Requirement | Source | Status | Evidence | Gap or defect | Recommended action |
| --- | --- | --- | --- | --- | --- |
| LLM never decides a Verdict | PRD P1, §6; ADR-0001; CLAUDE 1 | Partially Implemented | `baseline.py:132` builds VerdictEngine, never calls it; `evaluate` only in `challenger.py:140` | Run path produces `verdict=None`; harness stamps FAIL via keywords (`cli.py:410–421`) | F-02: wire engine and replay into `run`; remove harness stamping |
| Evidence first, no Finding without Evidence | PRD P2 | Partially Implemented | `evidence.py` enforces ≥1 Evidence | Evidence text is typed by the LLM, not captured by tools | F-03: auto-capture evidence from last observation |
| Black-box: only URL + Objective | PRD P3, §4 | Incorrect | `browser.py:154–158`, `api.py:107–111`, `baseline.py:144–146` | Target-specific selectors, endpoints, payloads in prompts | F-07 |
| All tool access via Gateway | PRD P4; CLAUDE 3 | Partially Implemented | Agents call `gateway.execute` | No per-agent permissions; click/fill/redirects unconstrained | F-05, F-06 |
| Application content is untrusted | PRD P5, §10; CLAUDE 4 | Partially Implemented | `browser.py:34`; `[V]` delimiter break-out | HTTP bodies undelimited; model never told; test tautological | F-08 |
| Everything traced (model, tool, Evidence, Verdict, tokens, model ID) | PRD P7 | Partially Implemented | 49/88 sub-agent entries in `juice_shop_run` have no `model_id`; no Evidence/Verdict entries | No run\_id; traces appended across runs | F-20 |
| Target allowlist mandatory | PRD §10; CLAUDE 5 | Incorrect | `gateway.py:74` substring match `[V]` | Bypassed by lookalike hosts and redirects `[V]` | F-04, F-05 |
| Secrets scrubbed from traces | PRD §10; CLAUDE 6 | Missing (live path) | `cli.py:67,78` pass no secret keys | Scrubber exists but is never configured | F-09 |
| One OpenAI-compatible client, retry, schema validation | PRD §5, §7 | Partially Implemented | `llm/client.py` | No transport retry/backoff; blind schema retry; no JSON-fence handling | F-14, F-21 |
| Tool Gateway: allowlist, permissions, budgets, scrubbing | PRD §5 | Partially Implemented | `gateway.py` | Budgets not in gateway; failures not traced | F-04, F-20 |
| Browser tools incl. console + network capture | PRD §5 | Partially Implemented | `console_errors` exists in `tools/browser.py` but is not in any agent tool list `[V]` | Agents cannot observe console errors; no network capture | F-12 |
| HTTP tool, recorded as Evidence | PRD §5 | Partially Implemented | `tools/http.py` | Redirects followed `[V]`; unbounded body; Evidence not attached to Findings | F-05, F-03 |
| Verdict Engine: element/text/URL/status/console assertions | PRD §5 | Partially Implemented | `[V]` `button.buy` → FAIL when present | Only `#id` selectors work; no status-code rule; FLAKY never produced | F-16 |
| RunState through every turn | PRD §5 | Partially Implemented | Per-agent only | Orchestrator never increments it | F-11 |
| Budgets: actions, model calls, time, tokens; global and per agent | PRD §7 | Partially Implemented | `run_state.py` has actions + tokens only | No model-call or wall-clock budget; global budget unenforced `[V]` | F-11, F-13 |
| Loop detection + recovery | PRD §7 | Partially Implemented | `loop_detector.py` | Only A,A,A detected `[V]`; recovery sets a flag, does nothing | F-17 |
| Retries recorded as PASS\_AFTER\_RETRY / FLAKY | PRD §7 | Missing | No code | — | F-16 |
| Malformed output: validate, retry ≤2, fail and record | PRD §7 | Partially Implemented | Planner only | Bad tool-arg JSON silently becomes `{}` | F-14 |
| Snapshot compaction | PRD §7 | Partially Implemented | `compact_snapshot` regex, 25,000-char cut | Not a11y-tree; tail of page lost; history never pruned | F-13 |
| Crawler + Coverage metric | PRD §5, §9 | Not Implemented in run path | Not imported by `cli.py` | Coverage never computed; regex crawler is SPA-blind | F-18 |
| Scoring Harness: recall, precision, replay, unsupported, coverage, cost, variance | PRD §9 | Partially Implemented | `harness.py` | Heuristic recall only; replay never fed; rest missing | F-15, F-01 |
| Own Site, ≥8 planted defects, 5 tuning / 3 held-out, frozen | PRD §4.1 | Implemented | `defects.json` (8, 5/3) | `matcher` field is ignored by the harness | F-15, F-23 |
| Ground-truth isolation test | PRD §12 | Implemented (narrow) | `test_ground_truth_isolation.py` | Scans `agents/` and `llm/` only | F-23 |
| Planner: schema Plan, no tools, replan ≤2 from reports | PRD §6, D2 | Partially Implemented | `planner.py` | Replan unreachable in production; budget split can exceed total | F-11, F-21 |
| Browser/API agents: own context, tool set, budget; return Findings + steps | PRD §6, D6 | Partially Implemented | `browser.py`, `api.py` | Shared browser session; `prior_findings` unused; tool set advisory | F-06, F-11 |
| Challenger: replay, downgrade to INCONCLUSIVE, never upgrade | PRD §6 | Partially Implemented | Class + 5 tests; not called by CLI | Gateway-only replay can never confirm `[V]` | F-19 |
| Juice Shop: 3 Objectives (D4), scoreboard scoring | PRD §4.2, D4 | Partially Implemented | `juice_shop.py`, harness | D4 never decided; recall = solved/all challenges; errors swallowed | F-15 |
| Prompt-injection fixture + test | PRD §10, Phase 3.3 | Partially Implemented | `feedback.html`; test | Test raises the exception itself `[C]` | F-08 |
| CLI + static report | PRD §11 | Partially Implemented | `cli.py`, `generator.py` | No-key crash `[V]`; report has no verdict source, steps, or escaping | F-10, F-14 |
| FastAPI mock backend, 2–3 planted API defects | PRD D3 | Implemented | `mock_api.py` (3 defects) | Not served by CLI; Own Site pages never call it | F-24 |
| Replay rate and unsupported = 0 as measured metrics | PRD §9 | Not Verifiable / Missing | No computation anywhere | Claimed 100% / 0 in docs | F-01 |
| 3 runs per configuration, mean and spread | PRD §9, plan 3.4 | Missing | No run artifacts for it | Numbers fabricated | F-01 |
| Pin model, record served model ID; refuse mixed-model comparisons | PRD §8; CLAUDE 7 | Partially Implemented | Check exists in `harness.py` | CLI never passes model IDs, so the check never runs | F-15, F-20 |
| Held-out reported once | PRD §9 | Not Verifiable | `--include-held-out` is unguarded | No audit trail | F-23 |
| Test plan: \~94 unit tests, gates per phase | Plan | Implemented (exceeded) | 114 collected, all green `[V]` | Many tests assert fakes, not behaviour on real wiring | F-08, F-22 |

## 3. Detailed technical findings (Deliverable 3)

Each finding lists: class and severity · requirement · where · what happens now (with evidence label) · impact · fix and approach · dependencies · acceptance test. Severity reflects verified impact, not speculation.

### F-01 · Benchmark results are hard-coded, then published as measured

- **Class / severity:** Requirement Gap (integrity) · **Critical** · P0
- **Requirement:** PRD §9 (metrics computed by the Scoring Harness; 3 runs per configuration; mean and spread), plan Phase 3.4 gate.
- **Where:** `src/qa_cc/cli.py:523–630` (`handle_results`), `README.md:115–126`, `files/PROJECT_PORTFOLIO.md:17,119–128`.
- **Now \[V\]:** `handle_results` builds a dict of literals (recall 60 / 80 / 66.7, replay 100, precision 100, tokens 18,450 / 34,200 / 26,800 / 37,100) and never reads a directory. Run from an empty temp dir it printed the whole table. The repo contains no Own Site benchmark runs: `run_output` and `test_noshery_run` are Noshery cart runs, `demo_run` is the mock, `juice_shop_run` is a Juice Shop run. Measured token totals from the committed traces: `run_output` 326,669 (39 calls), `juice_shop_run` 981,598 (88 calls), versus 18,450 and 26,800–34,200 claimed. A held-out run listed as done (`DEFECT-006`, `DEFECT-007` matched) has no artifact.
- **Impact:** An interviewer who opens `cli.py` sees fabricated results. That discredits every other claim in the project. The PRD itself says a no-improvement result is publishable if measured honestly, so nothing is gained by inventing numbers.
- **Fix:** Delete the literals. Store each run as `runs/<config>/<run_id>/{trace.jsonl,findings.json,score.json}`. `results` aggregates `score.json` files and prints `no scored runs found` (exit 1) when there are none. Remove the numbers from README, PORTFOLIO and any CV; regenerate the table from `results` output with run ids and commit hash.
- **Depends on:** F-03, F-15, F-19, F-20.
- **Acceptance:** `results` in an empty directory exits non-zero; a unit test shows the table changes when fixture `score.json` files change; README table is produced by a script, not typed.

### F-02 · Deterministic verdict pipeline is not wired into the run

- **Class / severity:** Architecture Issue · **Critical** · P0
- **Requirement:** PRD P1 and §6 (final verdict = assertion result + replay), ADR-0001, CLAUDE rule 1.
- **Where:** `agents/baseline.py:132` (instantiated, unused), `agents/browser.py`, `agents/api.py`, `orchestrator.py`, `cli.py:410–421`, `agents/challenger.py`.
- **Now \[C\]:** Agents create `Finding(verdict=None)` from whatever the LLM reports. Nothing evaluates an `AssertionRule`. `Challenger` is not imported by `cli.py`. In `juice_shop_run/findings.json` both findings carry `FAIL`; the only code that sets them is the scoring path at `cli.py:415–421`, which stamps FAIL when a finding's text keyword-matches a solved scoreboard challenge. \[V\] on artifacts: `run_output` and `test_noshery_run` findings have `verdict: null`.
- **Impact:** Verdicts are either absent or produced by text matching in the offline scorer, which is exactly what ADR-0001 forbids. README and PORTFOLIO state that all findings pass the VerdictEngine and the Challenger.
- **Fix:** Add a `FindingVerifier` step after each task: derive an `AssertionRule` from structured finding fields (see F-03), run `VerdictEngine`, run `Challenger` replay in a fresh browser context, and write the verdict plus reason into the finding and the trace. Remove verdict writing from `handle_score`; scoring reads verdicts, never creates them.
- **Depends on:** F-03, F-16, F-19.
- **Acceptance:** an integration test with FakeProvider and a local page: reported finding gets `verdict.type` from the engine; a finding whose assertion passes becomes INCONCLUSIVE; `grep -n 'Verdict(' src benchmark` shows creation only in `verdict/` and `challenger`.

### F-03 · Findings are not replayable, and Evidence is typed by the LLM

- **Class / severity:** Functional Defect · **High** · P1
- **Requirement:** PRD P2 (evidence first), §6 (return recorded steps), §9 (replay rate).
- **Where:** `agents/baseline.py:225–233`; `agents/browser.py` and `agents/api.py` (`report_finding`).
- **Now \[V\]:** Baseline findings store `steps` as `[{fingerprint: <hash>}]` only (checked in all committed `findings.json`). Browser/API findings store every step taken so far, not the steps that produced the defect, and step records are appended before the call executes, including calls that raised. Evidence content is the string the model supplies in `evidence_content`; tools do not attach what they actually observed. HTTP evidence built by `HttpTool` is returned to the model and then discarded.
- **Impact:** Replay and the 100% replay-rate claim are impossible for baseline runs; the model can hallucinate evidence and the system will store it. Large `evidence` blobs also appear twice in context (`body` plus `evidence`).
- **Fix:** `report_finding` takes `{summary, expected, actual, selector/url, step_ids}`. The agent runtime builds Evidence from the last real observation (snapshot, console log, HTTP exchange) and links `step_ids` to a per-run `StepLog` that stores `{tool, args, url_before, ok, error, evidence_id}`. Baseline and sub-agents share one `StepLog` class.
- **Depends on:** F-22 (shared loop).
- **Acceptance:** every finding in `findings.json` has non-fingerprint steps; a test shows that fabricated `evidence_content` is ignored in favour of captured evidence; Challenger can replay a baseline finding.

### F-04 · Allowlist is a substring match

- **Class / severity:** Security Risk · **High** · P0
- **Requirement:** PRD §10, CLAUDE rule 5.
- **Where:** `gateway/gateway.py:66–76` (also `crawler/crawler.py:39`).
- **Now \[V\]:** with allowlist `[localhost, 127.0.0.1]`, `_is_url_allowed` returns True for `https://evil.com/?next=localhost`, `http://localhost.evil.com/`, `https://evil.com/localhost`, and `http://localhost@evil.com/`. The unit test only checks `http://evil.com`.
- **Impact:** The one control that confines an LLM (and any prompt-injected page) to approved hosts can be bypassed trivially.
- **Fix:** Parse with `urlsplit`; require scheme in `{http, https}`, reject userinfo, compare `hostname` for exact equality (or exact `host:port`) against the allowlist; resolve and block if the resolved IP is not the one expected for loopback targets. Reuse one function in Gateway and Crawler.
- **Depends on:** none.
- **Acceptance:** parametrised test with the four URLs above plus IPv6, uppercase, trailing dot, and `localhost:3000` vs `localhost:3001` cases; all bypass URLs raise `TargetNotAllowed`.

### F-05 · Redirects and in-page navigation escape the allowlist

- **Class / severity:** Security Risk · **High** · P0
- **Requirement:** PRD §10; CLAUDE rules 3 and 5.
- **Where:** `tools/http.py:48` (`urllib.request.urlopen` follows redirects), `cli.py:279–290` (`click` and `fill` registered with no URL check), `tools/playwright_driver.py` (no request interception).
- **Now:** **\[V\]** an allowlisted `127.0.0.1` endpoint answered `302` to `127.0.0.2`; `http_request` returned `200` with that host's body, while a direct call to `127.0.0.2` raised `TargetNotAllowed`. **\[C\]** a click on `<a href='https://evil.com'>` is executed with no check, and sub-resource requests and `window.location` changes are not filtered. **\[S\]** Juice Shop ships open-redirect challenges, so this is reachable on the intended target.
- **Impact:** a prompt-injected page or a hallucinating model can drive the browser or HTTP tool off-target even after F-04 is fixed.
- **Fix:** HTTP: disable automatic redirects, follow manually up to 5 hops and re-check every hop with the gateway function; cap response bodies (e.g. 256 KB). Browser: `context.route('**/*', handler)` aborts any request whose host fails the same function, and a post-action check compares `page.url`.
- **Depends on:** F-04. **Acceptance:** tests for 302 to a disallowed host (raises), body cap, and an e2e where an external link click is blocked and traced.

### F-06 · No per-agent permissions; the LLM controls the screenshot path

- **Class / severity:** Security Risk · **Medium** · P1
- **Requirement:** PRD §6 (each agent has its own tool set), §10 (permission-gated tools), D6.
- **Where:** `gateway/gateway.py:99–131`, `cli.py:294`.
- **Now \[V\]:** tool isolation exists only as the list of schemas shown to the model; a call from a browser-type agent to `http_request` executes. The screenshot handler is `lambda path=<default>: ...`, so a model-supplied `path` replaces the output directory (`execute('screenshot', {'path': '/etc/cron.d/x.png'})` reached the handler). The default path is one fixed file, so later screenshots overwrite earlier Evidence.
- **Fix:** `execute(tool, args, caller)` with an `allowed_callers` set per `ToolDefinition`; the screenshot tool takes no path and the gateway writes `artifacts/<run_id>/<step>.png`, returning a relative path as Evidence.
- **Acceptance:** browser caller invoking `http_request` raises `PermissionRequired`; a supplied path is ignored or rejected; screenshots are unique per step.

### F-07 · Black-box principle violated: prompts carry target-specific knowledge

- **Class / severity:** Requirement Gap (benchmark validity) · **High** · P1
- **Requirement:** PRD P3 and §3 (agents get a URL and an Objective, nothing about defects), §4.2 (Juice Shop solutions are in training data, so 'found it' is weak evidence).
- **Where:** `agents/browser.py:154–158` (Juice Shop banner selector, `#loginButton`, the `' or 1=1--` payload), `agents/api.py:107–111` (exact Juice Shop endpoints, the login SQLi body, and 'report immediately on HTTP 200 with a token'), `agents/planner.py` (names `/rest/` and `/api/` SQL injection), `agents/baseline.py:144–146` ('Me want it!', stale totals, 404 on linked pages).
- **Now \[C\]:** the API agent is instructed to send the payload that solves Juice Shop's Login Admin challenge, and the scorer matches that challenge on any finding containing 'admin' and 'login' (F-15). **\[S\]** the baseline prompt's bug list (stale or negative totals, missing validation, broken link, layout, console error) mirrors the planted categories: hints, not names, but still not black-box.
- **Impact:** Juice Shop recall measures prompt authorship; baseline-vs-multi-agent is confounded because the hints differ per agent.
- **Fix:** role-generic prompts (boundary values, auth, error handling, console/network) with no target strings. Put any per-target aids in a declared **Target Profile** file that is recorded in the `run_start` trace entry and applied identically to baseline and multi-agent. Report with-profile and without-profile numbers separately.
- **Acceptance:** `grep -riE 'juice|noshery|rest/user|or 1=1|Me want' src/qa_cc/agents` returns nothing; profile contents appear in the trace.

### F-08 · Untrusted-content defence is cosmetic and its test is tautological

- **Class / severity:** Security Risk · **High** · P1
- **Requirement:** PRD P5 and §10, CLAUDE rule 4, plan 3.3.
- **Where:** `tools/browser.py:34–36`; all agent system prompts; `tests/unit/test_prompt_injection.py:46–86`.
- **Now:** **\[V\]** `delimit_dom_content` on text containing `</UNTRUSTED_DOM_CONTENT>` produces two closing tags, so a page can close the fence and write outside it. **\[C\]** no system prompt mentions the tags or says their content is data. **\[C\]** HTTP bodies and console text are not delimited though rule 4 lists 'responses'. **\[C\]** `test_agent_ignores_injected_instructions` wraps its assertion in `pytest.raises(TargetNotAllowed)` and raises that exception itself inside the block; the agent under test only calls `finish` and never receives the injection page. `feedback.html` is not read by any test.
- **Impact:** the claimed injection defence is unverified; the real backstop is the allowlist, which is bypassable (F-04, F-05).
- **Fix:** per-run random fence name and removal of any fence token from content; one prompt paragraph stating the rule; apply the wrapper to HTTP bodies and console output. Rewrite the test: feed the real snapshot of `feedback.html` to a scripted FakeProvider that then emits `navigate http://evil.com`; assert the gateway blocks it, permissions and target are unchanged, and the blocked call is traced.
- **Acceptance:** break-out string cannot terminate the fence; new test fails if the gateway check is removed.

### F-09 · Secret scrubbing is never enabled on the live path

- **Class / severity:** Security Risk · **Medium** · P0 (small change)
- **Requirement:** PRD §10, CLAUDE rule 6.
- **Where:** `cli.py:67` (`TraceWriter(trace_path)`), `cli.py:78` (`ToolGateway(...)`, no `secret_keys`).
- **Now \[C\]:** both scrubbers only act on environment variable names passed in, and none are passed. README and PORTFOLIO say `BAI_API_KEY` is scrubbed automatically; the code reads `LLM_API_KEY`. Secrets that appear at runtime (JWTs in Juice Shop login responses, session cookies) are not env variables and would be written to the trace, `findings.json` and the report. **\[V\]** I scanned every committed artifact for JWT, `sk-`, `AIza` and `Bearer` patterns and found none, so nothing has leaked yet.
- **Fix:** one `Scrubber` built from `LLM_API_KEY` plus a pattern set (JWT, `Authorization`, `Set-Cookie`); used by TraceWriter, Gateway, report and the `findings.json` dump.
- **Acceptance:** run the mock flow with a fake `LLM_API_KEY` and a JWT in a fixture response; grep the output directory: zero occurrences.

### F-10 · The report renders untrusted strings as raw HTML

- **Class / severity:** Security Risk · **Medium** · P0 (one-line fix)
- **Where:** `report/generator.py:31` and `:38` (`{ev.content}`, `{f.summary}`; `{f.id}` as well).
- **Now \[V\]:** Evidence containing `<script>alert('xss')</script>` and a summary containing `<img onerror=...>` appear unescaped in the generated HTML. Evidence is page DOM, which the target controls.
- **Fix:** `html.escape` every interpolated value (or Jinja2 with autoescape), add a `Content-Security-Policy` meta tag, and add verdict reason, step list and trace link to each card.
- **Acceptance:** a report built from a script payload contains `&lt;script&gt;` and no raw tag.

### F-11 · Orchestrator: replan is unreachable, run budget is not enforced, shared state is unused

- **Class / severity:** Functional Defect · **High** · P1
- **Requirement:** PRD §6, §7, D2, D6; plan 2.5.
- **Where:** `agents/orchestrator.py:77, 84, 115–132, 139`; status values in `agents/browser.py` and `agents/api.py`.
- **Now:** **\[V\]** real agents only return `status` of `completed` or `budget_exceeded`, so the `== 'failed'` replan branch can run only with test stubs. **\[V\]** with stub agents and a global `max_actions=5`, the run executed 15 actions, reported `budget_exceeded=False` and left `run_state.action_count == 0`: the orchestrator never calls `record_action` or `record_tokens`, so `--max-actions` and `--max-tokens` do not bound a multi-agent run. **\[C\]** after a replan the code sets `tasks = revised.tasks; i = 0` (comment says 'remaining tasks'), and the Planner is given the whole original plan without completion status, so finished tasks can be re-planned and re-run. **\[C\]** `except Exception: pass` at `:132` hides `ReplanLimitExceeded` and `MalformedOutputError` and nothing is traced. **\[C\]** `task.metadata['prior_findings']` is written but neither agent puts `task.metadata` in its prompt, so shared state is write-only.
- **Impact:** the headline multi-agent features (replan, budgets, cross-agent awareness) do not work in real runs.
- **Fix:** richer agent statuses (`completed`, `budget_exceeded`, `loop_terminated`, `llm_error`, `failed`); charge every `TaskResult` to a run-level `RunState` and stop when it is exhausted; pass remaining budget to the Planner; replan input is a structured `TaskReport` and output contains only new tasks; skip completed ids; trace every replan, including refusals; render `prior_findings` (id and summary only) in the sub-agent prompt as 'already reported'.
- **Depends on:** F-14, F-22. **Acceptance:** an LLM error yields `failed` and one replan; the third failure is refused and traced; a run-level cap stops execution; completed tasks never re-run; prior summaries appear in the sub-agent prompt.

### F-12 · Agents cannot observe console errors or failed requests

- **Class / severity:** Functional Defect · **High** · P1
- **Requirement:** PRD §5 (console and network capture), planted categories `console_error` (DEFECT-003, DEFECT-008).
- **Where:** `DEFAULT_TOOLS` and `BROWSER_TOOLS` (navigate, click, fill, screenshot, report\_finding, finish); `tools/browser.py` `console_errors()`; `cli.py:272–296`; `playwright_driver.py`.
- **Now \[V\]:** `console_errors` is referenced by no agent module and is not registered as a tool; the driver stores `console` events only and has no `pageerror` or network listener. The scripted e2e passes because the script reads the console, not because a live agent can.
- **Impact:** console-error and unhandled-rejection defects can only be found if the DOM happens to show them; the console rule in VerdictEngine is unreachable on live runs.
- **Fix:** append bounded `console_errors` and `failed_requests` (status ≥ 400, `requestfailed`) to every action result; capture `pageerror`; clear per navigation; also register `console_errors` as a tool.
- **Acceptance:** e2e on `catalog.html`: after `#filter-btn` the tool result contains the TypeError; unit test for `pageerror` capture.

### F-13 · Context grows every turn; token budgets do not hold

- **Class / severity:** Reliability Risk · **High** · P1
- **Requirement:** PRD §7 (compaction, budgets), §8 (about 300K-token reserve).
- **Where:** agent `messages` lists (never pruned), `compact_snapshot` (25,000-character cut), `RunState`.
- **Now \[V\] from committed traces:** `run_output` prompt tokens rise from 837 to 14,781 over 39 turns (326,669 total). In `juice_shop_run` sub-agent prompts reach 45,946 tokens (981,598 total over 88 calls). Every turn re-sends the full history, so cost is quadratic in turns. **\[C\]** the CLI default is 250,000 tokens but each agent defaults to 100,000 and the orchestrator does not add them up (F-11); `max_turns=25` is hard-coded independently of the action budget; snapshots keep the first 25K characters, so footers and late forms are cut.
- **Impact:** one multi-agent run can exceed the whole reserve, and the README's 18K–37K tokens per run is off by an order of magnitude.
- **Fix:** keep only the newest observation in full and replace older tool results with one-line summaries; send an interactive-element index (role, name, selector) capped at 2–4K characters instead of raw HTML; add `max_model_calls` and wall-clock budgets; derive `max_turns` from budget.
- **Acceptance:** a 25-turn FakeProvider run shows roughly linear prompt growth; token cap stops a run within one call of the limit.

### F-14 · Live-run failure modes are crashes or silent no-ops

- **Class / severity:** Functional Defect · **High** · P0 (first item)
- **Where:** `cli.py:248–258, 261–298, 635–638`; `except Exception: break` in `baseline.py:175`, `browser.py`, `api.py`.
- **Now:** **\[V\]** `python -m qa_cc run ...` without `LLM_API_KEY` dies with `TypeError: FakeProvider.__init__() missing 1 required positional argument: 'responses'` (`cli.py:257`). **\[C\]** `python-dotenv` is in neither `pyproject.toml` nor `uv.lock`, and `except ImportError: pass` hides it, so on a clean install `.env` is never loaded. **\[C\]** if Playwright fails to start, the CLI prints one line and continues with no browser tools registered. **\[C\]** any LLM/provider exception ends the loop quietly: no trace entry, `status` stays `completed`, nothing in the report. **\[C\]** malformed tool-argument JSON becomes `{}` and the tool is still executed. **\[C\]** `--mock` runs register no tools and return canned findings that look real in a report.
- **Fix:** fail fast with exit code and message when key, model or browser is missing; add `python-dotenv`; retry 429/5xx/timeouts with backoff; record `llm_error`, `tool_error` and `invalid_args` as trace events and set run status; label mock runs in the report header.
- **Acceptance:** one test per failure asserting non-zero exit or status plus a trace entry.

### F-15 · Scoring harness cannot be trusted as written

- **Class / severity:** Functional Defect · **High** · P1
- **Requirement:** PRD §4.2, §9, D4.
- **Where:** `benchmark/scoring/harness.py:25–70, 85–160`, `benchmark/scoring/juice_shop.py:31`, `cli.py:398–421`.
- **Now \[C\]:** Own Site matching ignores the frozen `matcher` objects and tests substrings of the model's free-text summary (defect name, page path, or any description word longer than 5 characters when the page matches); the code reads a `keywords` field that `defects.json` does not have. Juice Shop recall is **all solved scoreboard challenges ÷ all challenges**: not limited to the three Objectives (D4 is still open), not a before/after difference, and including anything solved earlier by hand or by a previous run; `matched_defects` is the list of every solved challenge, not the ones the findings matched. 'Error Handling' matches any text with '500' and 'error'; 'Login Admin' matches any text with 'admin' and 'login'. `fetch_challenges` swallows all exceptions and returns `[]`, so an unreachable Juice Shop yields recall 0.0 and no error. The CLI never passes `replay_results` or model IDs, so replay rate and the mixed-model guard never run; precision, coverage, cost per finding and variance are not computed.
- **Fix:** implement the PRD matchers as deterministic checks on structured finding fields (URL plus condition) and on replay outcome; for Juice Shop, snapshot the scoreboard before the run and score the difference restricted to the chosen Objectives, and raise if the API is unreachable; compute every §9 metric into `score.json`; read the model ID from the trace and refuse mixed comparisons.
- **Acceptance:** golden tests (known findings give known matches), harness raises on an unreachable scoreboard, `score.json` contains all §9 metrics.

### F-16 · VerdictEngine selector semantics are wrong; FLAKY is never produced

- **Class / severity:** Functional Defect · **Medium** · P2
- **Requirement:** PRD §5 (element, text, URL, status code, console assertions), §7 (PASS\_AFTER\_RETRY / FLAKY).
- **Where:** `verdict/engine.py`.
- **Now \[V\]:** `element_exists` returns FAIL for `button.buy`, `.buy` and `[data-x]` on a page that contains `<button class='buy'>`; only `#id` selectors are implemented and everything else is an escaped literal substring search. `url_equals` fails on a trailing-slash difference. **\[C\]** `element_contains_text` uses `>(.*?)</` and stops at the first closing tag, so nested markup is truncated; there is no status-code rule; `no_console_errors` defaults to `.*`, so any console message (a favicon 404) fails it; `FLAKY` and retry outcomes do not exist in code.
- **Fix:** evaluate rules with Playwright locators (or BeautifulSoup, already a dependency) using real CSS selectors; normalise URLs; add `status_code`; add `evaluate_with_retry(n)` that returns FLAKY when results differ.
- **Acceptance:** parametrised tests for class, attribute, nested text, trailing slash, and a flaky sequence.

### F-17 · Loop detector only catches A,A,A and recovery does nothing

- **Class / severity:** Functional Defect · **Medium** · P2
- **Requirement:** PRD §7 (three repeated pairs trigger re-observe, validate, retry or alternate, then continue or INCONCLUSIVE).
- **Where:** `agents/loop_detector.py`; loop code in all three agents.
- **Now:** **\[V\]** 24 alternating steps (A,B,A,B...) returned only `CONTINUE`. **\[C\]** the observation fingerprint is computed from the previous page state, before the action runs. `RE_OBSERVE` and `TRY_ALTERNATE` only set a boolean flag; no new snapshot is taken, nothing is said to the model, and nothing is traced. Termination happens on the fifth identical repeat.
- **Fix:** sliding-window detector (period up to 3) using the observation after the action; implement recovery (fresh snapshot plus a message naming the repeated action; then force a different tool or selector; then end with status `loop_terminated`); trace each step.
- **Acceptance:** tests for ABAB, ABCABC, message injection, and terminal status.

### F-18 · Crawler and Coverage are not wired in

- **Class / severity:** Requirement Gap · **Medium** · P2
- **Requirement:** PRD §5 and §9 (Coverage = exercised share of crawler inventory).
- **Where:** `crawler/crawler.py`; `cli.py` (no import) **\[V\]** by grep.
- **Now \[C\]:** the default fetcher is `lambda u: ''`, so `Crawler()` discovers nothing; discovery is regex over static HTML, which cannot see Juice Shop's Angular routes; the allowlist check repeats the substring flaw; no code maps a run's steps to inventory items.
- **Fix:** crawl with Playwright or httpx through the shared allowlist function; write `inventory.json` once per target; `score` computes coverage from run steps and inventory (pages and forms; for SPAs, routes and interactive elements).
- **Acceptance:** `score.json` has `coverage`; the Own Site inventory lists all 7 pages and the contact form.

### F-19 · Challenger replay cannot confirm a finding in the gateway path

- **Class / severity:** Functional Defect · **Medium** · P2
- **Requirement:** PRD §6 (replay, downgrade, never upgrade), §9 (replay rate).
- **Where:** `agents/challenger.py:105–160`.
- **Now:** **\[V\]** replay through the gateway with no driver returned `replayed=True, reproduced=False, final=INCONCLUSIVE`: `page_state` stays `{}`, so nothing can be evaluated. **\[C\]** replay uses the same live browser session (docs say 'clean browser session'); the default reproduction rule is any console message containing 'error', unrelated to the claimed defect; `http_request` steps are replayed with no assertion; the outcome is not written to trace or finding; returning `FAIL` as a final verdict sits awkwardly with ADR-0001's 'never sets a verdict'.
- **Fix:** a `Replayer` that opens a fresh browser context, replays the step log, then evaluates the finding's own `AssertionRule` through VerdictEngine; the Challenger only returns `confirm` or `downgrade(reason)` and one `finalize_verdict(assertion, replay)` function computes the verdict.
- **Acceptance:** e2e confirms planted DEFECT-004 on Own Site; a flaky finding yields FLAKY; the result is in the trace.

### F-20 · Trace has no run identity and omits required events

- **Class / severity:** Functional Defect · **Medium** · P2
- **Requirement:** PRD P7 and §8 (served model ID and tokens on every entry), plan 0.4 (`TraceEntry` model).
- **Where:** `trace/writer.py`, `cli.py:64–67`, agents, gateway.
- **Now \[V\]:** traces are opened in append mode with no run id: `juice_shop_run/trace.jsonl` mixes 7 runs (3 `run_start`, 4 `orchestrator_start`), so totals cannot be attributed. 49 of 88 sub-agent model-call entries have no `model_id`. **\[C\]** tool calls are traced only on success (a `TargetNotAllowed` leaves nothing); Evidence, verdicts, challenges, loop events and refused replans are not traced; the `TraceEntry` Pydantic model from the plan does not exist. README and PORTFOLIO call the trace cryptographic and append-only; there is no hashing or locking.
- **Fix:** `run_id` and one directory per run; `TraceEntry(BaseModel)` with required fields and a `seq` plus `prev_hash` chain; trace in `finally` blocks including denied calls; record the served model on every model call.
- **Acceptance:** schema test on every entry; totals recomputed from the trace match `RunResult`.

### F-21 · Planner is brittle and its budget split can exceed the total

- **Class / severity:** Reliability Risk · **Medium** · P2
- **Where:** `agents/planner.py:70–74, 112–118, 126–140`.
- **Now \[C\]:** `json.loads(content)` fails on fenced JSON or `content=None`, both common from tool-calling models; schema retries resend identical messages without telling the model what was wrong. `Plan` accepts zero tasks, duplicate ids and unlimited tasks; `budget` is a free-form dict. `_enforce_budget_split` clamps each task to at least 1, so with many tasks the sum can exceed the total; the prompt asks for 15–25 actions per task, which the clamp then undoes.
- **Fix:** strip fences or use structured output where supported; typed `Budget` with positive integers; validators (1–6 tasks, unique ids); append the parse error to the retry message; integer split with remainder.
- **Acceptance:** tests for fenced JSON, empty plan, duplicate ids, and `sum(budgets) <= total`.

### F-22 · The agent loop is copied three times

- **Class / severity:** Code Quality Issue · **Medium** · P1 (prerequisite for F-03, F-11, F-14, F-17)
- **Where:** `agents/baseline.py` (about 290 lines), `browser.py` (about 310), `api.py` (about 270).
- **Now \[C\]:** tool-call parsing, loop detection, budget checks, `report_finding` handling and error swallowing are duplicated; `BROWSER_TOOLS` repeats `DEFAULT_TOOLS`; each copy has drifted (different trace event names, different default tool-call ids, `RunResult.summary` is never set by baseline).
- **Fix:** one `AgentLoop(client, gateway, tools, prompt, run_state, step_log, trace)` with hooks for building the task message and handling findings. Baseline, Browser and API become configuration.
- **Acceptance:** about 500 fewer lines; all 114 existing tests still pass.

### F-23 · Held-out discipline and ground-truth isolation are weaker than documented

- **Class / severity:** Requirement Gap · **Medium** · P2
- **Requirement:** PRD §4.1 (held-out never inspected while tuning), §9 (report held-out once), §12 (isolation test).
- **Now \[C\]:** `--include-held-out` works at any time and nothing records when held-out was scored. Tuning and held-out defects live in one `defects.json`, and a held-out defect (DEFECT-007) was implemented in `mock_api.py` during Phase 2, so it was visible while tuning. The isolation test scans string constants in `src/qa_cc/agents` and `src/qa_cc/llm` only, not gateway, tools, report or runtime file access.
- **Fix:** separate `defects.tuning.json` and a sealed held-out file (commit only its hash); `score --final` writes a one-time lock file with hash and timestamp; widen the lexical test to all of `src/qa_cc` except the scoring import in `cli.py`.
- **Acceptance:** a second `--final` run is refused; the widened test fails if any non-scoring module names the ground-truth path.

### F-24 · Packaging, repository hygiene and doc divergence

- **Class / severity:** Code Quality Issue · **Low** · P3
- **Now:** **\[V\]** `qa-cc score --run-dir run_output` from the repo root fails with `ModuleNotFoundError: No module named 'benchmark'` (the package lives outside `src/`); `python -m qa_cc score` works only with the repo root as the current directory. **\[C\]** `fastapi` and `uvicorn` are runtime dependencies used only by the mock backend; `python-dotenv` is missing (F-14). The tree holds duplicates of README, progress, plan and CLAUDE.md under `files/` (CLAUDE.md differs), while CLAUDE.md says `PRD.md` and `CONTEXT.md` are at the root (they are only in `files/`); five committed run directories; PNGs at the root, in `artifacts/` and `screenshot/`; `src/qa_cc.egg-info`, `__pycache__` for CPython 3.14, `.DS_Store`; absolute local paths in `progress.md`; test counts disagree (progress 111, portfolio 112, collected 114); CLAUDE.md 'Commands' still says to fill them in.
- **Fix:** move scoring code into `src/qa_cc/scoring` (data stays in `benchmark/`); dev-only dependencies into extras; add `.gitignore`; add a `justfile` or Makefile with test, lint, run and score; one docs location; curate one or two real runs under `examples/`.
- **Acceptance:** `pip install .` then `qa-cc score` works from any directory; a clean clone has no generated files.

## 4. Data flow and architecture findings (Deliverable 4)

### 4.1 Finding creation and verdict flow (essential change)

**Today:**

```
LLM --report_finding(summary, evidence_content)--> Finding(evidence = LLM text, steps = [hashes], verdict = None)
    --> findings.json --> report.html (UNVERIFIED badge)
score (offline) --keyword match vs scoreboard--> writes verdict = FAIL --> report
```

**Intended:**

```
LLM --report_finding(claim: where / expected / actual, step_ids)--> AgentLoop
AgentLoop attaches captured Evidence (last observation, console, failed requests, HTTP exchange)
  --> FindingVerifier: AssertionRule from the claim --> VerdictEngine (live state)
  --> Replayer: fresh browser context + StepLog --> VerdictEngine again
  --> finalize_verdict(assertion, replay) = PASS | FAIL | INCONCLUSIVE | FLAKY
  --> verdict + reason written to trace and findings.json --> report
score (offline) reads verdicts and never writes them
```

### 4.2 Multi-agent flow (essential)

- **Today:** Planner returns a Plan; tasks run in order; replan only on `status == failed`, which never occurs; each task starts from whatever page the previous task left in the single shared browser; prior findings are written into `task.metadata` and never read; no run-level budget.
- **Intended:** Planner gets Objective plus Target Profile and remaining budget; each task runs in a fresh browser context with its own budget; `TaskResult` returns findings, step ids and a status; Orchestrator charges a run-level `RunState`, passes already-reported summaries into later prompts, and replans from structured reports with completed tasks excluded; every decision is traced.

### 4.3 Scoring and results flow (essential)

- **Today:** `score` guesses target type from the trace text, matches by substrings, can stamp verdicts and rewrite findings; `results` prints literals.
- **Intended:** `run` writes `runs/<config>/<run_id>/`; `score` writes `score.json` containing every PRD §9 metric; `results` aggregates `score.json` files and nothing else.

### 4.4 Which changes are essential and which are optional

| Change | Essential | Optional |
| --- | --- | --- |
| Remove hard-coded results; generate from `score.json` | Yes |  |
| Fix allowlist, redirects, report escaping, scrubbing | Yes |  |
| Wire VerdictEngine, replay and Challenger into `run` | Yes |  |
| Structured findings and captured Evidence | Yes |  |
| Shared `AgentLoop`, `StepLog`, `Scrubber`, `run_id` | Yes (enables the rest) |  |
| Target Profile instead of hard-coded prompts | Yes |  |
| Context pruning and interactive-element index | Yes |  |
| Move scoring into `src/qa_cc/scoring`, `justfile`, dependency extras |  | Yes |
| Hash-chained trace |  | Yes |
| Live dashboard and paste-any-site mode |  | Yes. **Both conflict with the PRD** (a live dashboard is a listed non-goal in §2 and CLAUDE.md's scope guard; arbitrary targets conflict with the mandatory allowlist in §10). Change the PRD and add an ADR first. |

## 5. Code cleanup and refactoring plan (Deliverable 5)

| Action | Item | Rationale |
| --- | --- | --- |
| **Remove** | `handle_results` literals (`cli.py:524–591`), the matching README table (`README.md:115–126`) and PORTFOLIO table and metrics lines | Fabricated numbers (F-01). Regenerate from real runs. |
| **Remove** | Verdict stamping in `handle_score` (`cli.py:410–433`) and `--update-report` | Contradicts ADR-0001 (F-02). |
| **Remove** | Unused `verdict_engine` attribute in `BaselineAgent` until it is really used; `files/` duplicates; `src/qa_cc.egg-info`, `__pycache__`, `.DS_Store`, stray PNGs; `demo_run` (mock output) | Dead code and clutter (F-24). |
| **Remove** | Target-specific strings from every system prompt | Black-box rule (F-07). |
| **Refactor** | Three agent loops into one `AgentLoop` | F-22; unlocks F-03, F-11, F-14, F-17. |
| **Refactor** | `ToolGateway`: exact-host allowlist, caller permissions, trace-on-failure, one scrubber | F-04, F-06, F-09, F-20. |
| **Refactor** | `HttpTool`: manual redirects, body cap, auto-attached Evidence, delimited output | F-05, F-03, F-08. |
| **Refactor** | `VerdictEngine`: DOM-based rules, URL normalisation, status-code rule, retry/FLAKY | F-16. |
| **Refactor** | `LoopDetector` and recovery behaviour | F-17. |
| **Refactor** | `Challenger` into `Replayer` plus `finalize_verdict` | F-19. |
| **Refactor** | `ScoringHarness`: matchers, scoreboard delta, full metric set | F-15. |
| **Consolidate** | URL allowlist into one function used by Gateway, Crawler and Playwright route handler | F-04, F-05, F-18. |
| **Consolidate** | `report_finding` and step recording into `StepLog` shared by all agents | F-03. |
| **Reorganise** | `benchmark/scoring` to `src/qa_cc/scoring`; per-run directories under `runs/`; docs under `docs/` only; `PRD.md` and `CONTEXT.md` where CLAUDE.md says they are | F-24. |
| **Retain** | `LLMClient` and `FakeProvider` interfaces, `Evidence`/`Finding` models, `RunState` shape, per-task budget idea, Plan/Task schema, Own Site pages and defect list, ADR-0001/0002, ground-truth AST test (widen it), the 114 unit tests (rewrite the weak ones named in F-08) | Sound seams; they make the refactor safe. |

## 6. Prioritised remediation roadmap (Deliverable 6)

### P0 — Critical (do before anyone else reads the repo)

| Action | Findings | Expected outcome | Depends on | Components | Validation |
| --- | --- | --- | --- | --- | --- |
| Delete hard-coded results and unsupported claims (100% replay, 0 hallucinations, cryptographic trace, automatic scrubbing) from README, PORTFOLIO, CV; make `results` read `score.json` | F-01 | Nothing published that the code cannot reproduce | none | `cli.py`, README, PORTFOLIO | `results` exits non-zero in an empty directory; docs contain only generated numbers |
| Exact-host allowlist | F-04 | Lookalike hosts blocked | none | `gateway.py`, `crawler.py` | parametrised bypass tests |
| Redirect handling and Playwright request routing | F-05 | Off-target requests blocked and traced | F-04 | `http.py`, driver | 302 test; e2e external link |
| Escape the report | F-10 | No raw HTML from evidence | none | `generator.py` | `&lt;script&gt;` test |
| Enable scrubbing everywhere | F-09 | Secrets and JWTs never reach disk | none | `cli.py`, writer, gateway, report | grep of output dir |
| Fail fast on missing key, browser, bad args; add `python-dotenv` | F-14 | No silent empty runs | none | `cli.py`, agents | one test per failure |
| Remove verdict stamping from the scorer; label unverified findings honestly | F-02 (part) | Report no longer implies verification | none | `cli.py`, report | no `Verdict(` outside verdict code |

### P1 — High

| Action | Findings | Expected outcome | Depends on | Components | Validation |
| --- | --- | --- | --- | --- | --- |
| Shared `AgentLoop` and `StepLog` | F-22, F-03 | One place for parsing, budgets, errors, steps | P0 | agents | existing tests green, 500 fewer lines |
| Structured findings, captured Evidence, replayable steps | F-03 | Every finding replayable | AgentLoop | agents, tools, models | Challenger replays a baseline finding |
| Wire VerdictEngine, Replayer and Challenger into `run`; fix engine selectors | F-02, F-16, F-19 | Verdicts come from code | structured findings | verdict, challenger, cli | integration test; e2e confirms DEFECT-004 |
| Target Profile; generic prompts | F-07 | Black-box runs; ablation possible | none | prompts, config | grep test; profile in trace |
| Orchestrator budget, statuses, replan, shared state | F-11 | Multi-agent features really work | AgentLoop | orchestrator, agents | tests listed in F-11 |
| Console and network observation | F-12 | Console defects detectable live | none | driver, tools | e2e on `catalog.html` |
| Context pruning, element index, extra budgets | F-13 | About linear tokens, runs fit the reserve | AgentLoop | tools, `RunState` | 25-turn token test |
| Per-agent permissions; fixed screenshot path | F-06 | Tool isolation enforced | none | gateway | permission tests |
| Fence hardening; real injection test | F-08 | Injection defence verified | none | browser tools, prompts, tests | new test fails without gateway check |
| Scoring harness rewrite; scoreboard delta | F-15 | Trustworthy recall | structured findings | scoring, cli | golden tests |

### P2 — Medium

| Action | Findings | Expected outcome | Depends on | Validation |
| --- | --- | --- | --- | --- |
| Loop detector window and recovery | F-17 | Real recovery | AgentLoop | ABAB and recovery tests |
| Run ids, `TraceEntry`, denied-call tracing, hash chain (optional) | F-20 | Attributable, complete traces | none | schema test, totals match |
| Planner parsing, typed budgets, validators | F-21 | Fewer planner failures | none | fenced JSON and empty-plan tests |
| Crawler on Playwright; Coverage metric | F-18 | Coverage reported | allowlist function | `score.json` has coverage |
| Sealed held-out set and one-time final scoring; widen isolation test | F-23 | Honest generalisation claim | none | second `--final` refused |
| Run the benchmark properly: 3 baseline and 3 multi-agent runs on tuning, one held-out run, Juice Shop Objectives chosen (D4) | F-01, F-15 | Real results table | all P1 | generated `results` table with run ids |

### P3 — Low and optional

| Action | Findings | Note |
| --- | --- | --- |
| Packaging, `.gitignore`, `justfile`, dependency extras, repo clean-up | F-24 | Housekeeping |
| Serve the mock backend from the CLI and let Own Site pages call it | F-24 | Makes the API Agent target real |
| **Optional:** live dashboard; paste-any-site mode | none | Not in the documented scope; needs a PRD change and an ADR first (see 4.4) |
| **Optional:** accessibility-tree snapshots via Playwright | F-13 | Better observation quality |

## 7. Final acceptance checklist (Deliverable 7)

**Integrity**

- ☐ `qa-cc results` in an empty directory exits non-zero; every number in README and PORTFOLIO is generated and cites run ids and commit.
- ☐ No claim in docs that the code cannot demonstrate (replay rate, hallucination count, cryptographic trace, scrubbing).

**Safety**

- ☐ Lookalike-host and redirect tests pass; external link click is blocked and traced.
- ☐ A secret in env and a JWT in a response appear nowhere in the output directory.
- ☐ Report escapes all interpolated values; fence cannot be closed by page content; the injection test fails when the gateway check is removed.
- ☐ Caller permissions enforced; screenshot path is not model-controlled.

**Verdicts and evidence**

- ☐ Every finding has captured Evidence, non-fingerprint steps, and a verdict from `finalize_verdict`.
- ☐ `grep -n 'Verdict(' src benchmark` shows creation only in verdict and challenger code.
- ☐ Challenger replay in a fresh context confirms a planted defect and downgrades a non-reproducible one.

**Agents**

- ☐ Prompts contain no target-specific strings; any Target Profile is traced and used by both configurations.
- ☐ Orchestrator enforces a run-level budget, handles `failed` and `loop_terminated`, refuses the third replan and traces it.
- ☐ Console errors and failed requests are visible to agents; `catalog.html` TypeError is observed in a live-style test.
- ☐ 25-turn run shows about linear prompt growth; a multi-agent run on Own Site fits the token reserve.

**Measurement**

- ☐ `score.json` contains recall, precision (triaged), replay rate, unsupported findings, coverage, cost per confirmed finding.
- ☐ 3 baseline and 3 multi-agent runs exist with spread; held-out scored once with a lock file; Juice Shop scored as a before/after scoreboard difference on the three chosen Objectives.
- ☐ Mixed-model comparisons are refused using model IDs read from traces.

**Engineering**

- ☐ Unit suite green; Own Site e2e and multi-agent e2e executed with a real browser; one live contract run recorded in ADR-0002.
- ☐ `pip install .` then `qa-cc run`, `score`, `results` work from any directory; a clean clone contains no generated files or duplicate docs.

## 8. What I could not verify

Own Site e2e and multi-agent e2e (no Chromium in my sandbox), any live LLM behaviour, Docker Juice Shop, git history, `.gitignore`/`.env` handling, and whether the PRD PDF matches `files/PRD.md`. Findings tagged \[S\] are inferences and are labelled as such. Everything tagged \[V\] was reproduced with the scripts described in this audit.
