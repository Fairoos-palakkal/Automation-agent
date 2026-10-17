import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import List, Optional
from urllib.parse import urlparse
import uuid

from qa_cc.agents.baseline import BaselineAgent, RunResult
from qa_cc.agents.plan import Plan, Task, AgentType
from qa_cc.agents.planner import Planner
from qa_cc.agents.browser import BrowserAgent
from qa_cc.agents.api import APIAgent
from qa_cc.agents.orchestrator import Orchestrator
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.report.generator import generate_report
from qa_cc.security.scrubber import Scrubber
from qa_cc.tools.http import HttpTool
from qa_cc.trace.run_state import RunState
from qa_cc.trace.writer import TraceWriter
from qa_cc.config.target_profile import TargetProfile
from qa_cc.verdict.evidence import Evidence, EvidenceType, Finding
from qa_cc.verdict.engine import VerdictEngine
from qa_cc.verdict.replayer import Replayer
from qa_cc.verdict.verifier import FindingVerifier


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qa_cc",
        description="Agentic QA Command Center — Autonomous Testing & Evidence Capture",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Run subcommand
    run_parser = subparsers.add_parser("run", help="Execute an autonomous QA run against a target")
    run_parser.add_argument("--target", required=True, help="Target URL (e.g. http://localhost:3000)")
    run_parser.add_argument("--objective", required=True, help="Natural language objective")
    run_parser.add_argument("--output-dir", default=None, help="Directory for trace and reports (defaults to runs/<config>/<run_id>)")
    run_parser.add_argument("--run-id", default=None, help="Attributable Run identifier (defaults to generated run-YYYYMMDD-HHMMSS-<id>)")
    run_parser.add_argument("--mock", action="store_true", help="Use deterministic mock provider for testing")
    run_parser.add_argument("--multi-agent", action="store_true", help="Run with Planner + BrowserAgent + APIAgent")
    run_parser.add_argument("--max-actions", type=int, default=25, help="Action budget limit")
    run_parser.add_argument("--max-tokens", type=int, default=250_000, help="Total token budget limit across run")
    run_parser.add_argument("--allowlist", nargs="*", default=[], help="Additional allowed hostnames for tool access")
    run_parser.add_argument("--profile", default=None, help="Path to Target Profile JSON file")

    # Score subcommand
    score_parser = subparsers.add_parser("score", help="Score findings from a completed run against ground truth")
    score_parser.add_argument("--run-dir", required=True, help="Directory containing run artifacts")
    score_parser.add_argument("--compare", help="Second run directory for comparative evaluation")
    score_parser.add_argument("--ground-truth", default="benchmark/ground_truth/defects.json", help="Path to ground truth defects.json")
    score_parser.add_argument("--include-held-out", action="store_true", help="Include held-out evaluation defects")
    score_parser.add_argument("--target-type", choices=["own_site", "juice_shop"], default=None, help="Target application type (own_site or juice_shop)")
    score_parser.add_argument("--scoreboard-url", default="http://localhost:3000/api/Challenges", help="Juice Shop challenges API URL")

    # Results subcommand
    results_parser = subparsers.add_parser("results", help="Display benchmark results and comparative table")
    results_parser.add_argument("--runs-dir", default="runs", help="Directory containing config run directories")
    results_parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format")
    results_parser.add_argument("--include-held-out", action="store_true", help="Include held-out evaluation defects in results")

    return parser


def handle_run(args: argparse.Namespace) -> int:
    config = "multi_agent" if args.multi_agent else "baseline"
    run_id = args.run_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = Path("runs") / config / run_id

    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.jsonl"
    report_path = out_dir / "report.html"

    scrubber = Scrubber(secret_env_vars=["LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"])
    trace_writer = TraceWriter(trace_path, scrubber=scrubber, run_id=run_id)
    run_state = RunState(max_actions=args.max_actions, max_tokens=args.max_tokens)
    target_profile = TargetProfile.load(args.profile) if getattr(args, "profile", None) else None


    target_parsed = urlparse(args.target)
    allowlist = ["localhost", "127.0.0.1"]
    if target_parsed.hostname and target_parsed.hostname not in allowlist:
        allowlist.append(target_parsed.hostname)
    for extra in args.allowlist:
        if extra not in allowlist:
            allowlist.append(extra)

    gateway = ToolGateway(
        allowlist=allowlist,
        trace_writer=trace_writer,
        scrubber=scrubber,
        artifacts_dir=out_dir,
    )

    browser_instance = None
    playwright_ctx = None

    if args.mock:
        if args.multi_agent:
            # Scripted providers for multi-agent mock run
            planner_plan = {
                "objective": args.objective,
                "tasks": [
                    {
                        "id": "task-b",
                        "goal": "Mock browser exploration",
                        "assignee": "browser",
                        "budget": {"max_actions": 5, "max_tokens": 5000},
                    },
                    {
                        "id": "task-a",
                        "goal": "Mock API testing",
                        "assignee": "api",
                        "budget": {"max_actions": 5, "max_tokens": 5000},
                    },
                ],
            }
            planner_client = LLMClient(provider=FakeProvider(responses=[{
                "id": "pl-1",
                "model": "fake-planner",
                "choices": [{"message": {"role": "assistant", "content": json.dumps(planner_plan)}}],
            }]))
            planner = Planner(llm_client=planner_client)

            browser_client = LLMClient(provider=FakeProvider(responses=[
                {
                    "id": "b-1",
                    "model": "fake-browser",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "tc-b",
                                "type": "function",
                                "function": {
                                    "name": "report_finding",
                                    "arguments": {
                                        "summary": "Mock UI defect found",
                                        "evidence_type": "dom_snapshot",
                                        "evidence_content": "<button>Error</button>",
                                    },
                                },
                            }],
                        }
                    }],
                },
                {
                    "id": "b-2",
                    "model": "fake-browser",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "tc-b2",
                                "type": "function",
                                "function": {"name": "finish", "arguments": {"summary": "Browser finished"}},
                            }],
                        }
                    }],
                },
            ]))

            api_client = LLMClient(provider=FakeProvider(responses=[
                {
                    "id": "a-1",
                    "model": "fake-api",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "tc-a",
                                "type": "function",
                                "function": {
                                    "name": "report_finding",
                                    "arguments": {
                                        "summary": "Mock API defect found",
                                        "evidence_type": "network_request",
                                        "evidence_content": "500 Internal Error",
                                    },
                                },
                            }],
                        }
                    }],
                },
                {
                    "id": "a-2",
                    "model": "fake-api",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "tc-a2",
                                "type": "function",
                                "function": {"name": "finish", "arguments": {"summary": "API finished"}},
                            }],
                        }
                    }],
                },
            ]))

            browser_agent = BrowserAgent(llm_client=browser_client, gateway=gateway, trace_writer=trace_writer)
            api_agent = APIAgent(llm_client=api_client, gateway=gateway, trace_writer=trace_writer)

            orchestrator = Orchestrator(
                planner=planner,
                browser_agent=browser_agent,
                api_agent=api_agent,
                trace_writer=trace_writer,
                run_state=run_state,
            )
            result = orchestrator.run(objective=args.objective, target=args.target, target_profile=target_profile)
            result.is_mock = True
        else:
            # Baseline single-agent mock
            canned = [
                {
                    "id": "canned-1",
                    "model": "fake-canned",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "c1",
                                "type": "function",
                                "function": {
                                    "name": "report_finding",
                                    "arguments": {
                                        "summary": "Mock verification finding",
                                        "evidence_type": "dom_snapshot",
                                        "evidence_content": "<div>Mock element</div>",
                                    },
                                },
                            }],
                        }
                    }],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                },
                {
                    "id": "canned-2",
                    "model": "fake-canned",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "c2",
                                "type": "function",
                                "function": {"name": "finish", "arguments": {"summary": "Done"}},
                            }],
                        }
                    }],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
                },
            ]
            provider = FakeProvider(responses=canned)
            client = LLMClient(provider=provider)
            agent = BaselineAgent(
                llm_client=client,
                gateway=gateway,
                run_state=run_state,
                trace_writer=trace_writer,
                target_profile=target_profile,
            )
            result = agent.run(objective=args.objective, target=args.target)
            result.is_mock = True
    else:
        api_key = os.environ.get("LLM_API_KEY", "")
        if not api_key or api_key == "your_api_key_here":
            print(
                "Error: Missing LLM_API_KEY. Please set LLM_API_KEY in your environment or .env file, or use --mock for simulated runs.",
                file=sys.stderr,
            )
            return 1

        from qa_cc.llm.openai_provider import OpenAICompatibleProvider
        provider = OpenAICompatibleProvider(
            base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
            api_key=api_key,
            model=os.environ.get("LLM_MODEL", "Qwen3.8-Flash"),
        )
        client = LLMClient(provider=provider)

        # Wire live Playwright browser
        try:
            from playwright.sync_api import sync_playwright
            from qa_cc.tools.playwright_driver import PlaywrightPageDriver
            from qa_cc.tools.browser import BrowserTools

            playwright_ctx = sync_playwright().start()
            browser_instance = playwright_ctx.chromium.launch(headless=True)
            page = browser_instance.new_page()
            driver = PlaywrightPageDriver(page, allowlist=allowlist, trace_writer=trace_writer)
            browser_tools = BrowserTools(driver)

            gateway.register_tool(
                ToolDefinition(
                    name="navigate",
                    handler=browser_tools.navigate,
                    is_url_action=True,
                    allowed_callers={"baseline", "browser"},
                )
            )
            gateway.register_tool(
                ToolDefinition(
                    name="click",
                    handler=browser_tools.click,
                    allowed_callers={"baseline", "browser"},
                )
            )
            gateway.register_tool(
                ToolDefinition(
                    name="fill",
                    handler=browser_tools.fill,
                    allowed_callers={"baseline", "browser"},
                )
            )
            gateway.register_screenshot_tool(
                browser_tools.screenshot,
                allowed_callers={"baseline", "browser"},
            )
        except Exception as e:
            if playwright_ctx:
                try:
                    playwright_ctx.stop()
                except Exception:
                    pass
            print(f"Error: Failed to initialize browser: {e}. Run 'playwright install chromium' to install browser binaries.", file=sys.stderr)
            return 1

        # Wire HTTP tool
        http_tool = HttpTool(allowlist=allowlist, delimit=True)
        gateway.register_tool(
            ToolDefinition(
                name="http_request",
                handler=http_tool.request,
                is_url_action=True,
                allowed_callers={"baseline", "api"},
            )
        )

        if args.multi_agent:
            planner = Planner(llm_client=client)
            browser_agent = BrowserAgent(llm_client=client, gateway=gateway, trace_writer=trace_writer)
            api_agent = APIAgent(llm_client=client, gateway=gateway, trace_writer=trace_writer)
            orchestrator = Orchestrator(
                planner=planner,
                browser_agent=browser_agent,
                api_agent=api_agent,
                trace_writer=trace_writer,
                run_state=run_state,
            )
            result = orchestrator.run(objective=args.objective, target=args.target, target_profile=target_profile)
        else:
            agent = BaselineAgent(
                llm_client=client,
                gateway=gateway,
                run_state=run_state,
                trace_writer=trace_writer,
                target_profile=target_profile,
            )
            result = agent.run(objective=args.objective, target=args.target)

    # Deterministic verdict pipeline: FindingVerifier + Replayer
    replayer = None
    if browser_instance:
        replayer = Replayer(browser=browser_instance, trace_writer=trace_writer)
    elif args.mock:
        replayer = Replayer(trace_writer=trace_writer)

    verifier = FindingVerifier(
        verdict_engine=VerdictEngine(),
        replayer=replayer,
        trace_writer=trace_writer,
    )
    result.findings = verifier.verify_findings(result.findings)

    if browser_instance:
        browser_instance.close()
    if playwright_ctx:
        playwright_ctx.stop()

    # Save findings JSON
    findings_path = out_dir / "findings.json"
    with open(findings_path, "w", encoding="utf-8") as f:
        json.dump([scrubber.scrub(finding.model_dump()) for finding in result.findings], f, indent=2)

    generate_report(result, report_path, scrubber=scrubber)
    print(f"Run completed. Actions: {result.actions_count}, Findings: {len(result.findings)}")
    print(f"Trace saved to {trace_path}")
    print(f"Findings saved to {findings_path}")
    print(f"Report saved to {report_path}")
    return 0


def _save_score_json(run_dir: Path, target_type: str, report: Any, findings: List[Any], is_held_out: bool = False) -> None:
    score_data = {
        "run_id": run_dir.name,
        "target_type": target_type,
        "recall": report.recall,
        "recall_pct": round(report.recall * 100.0, 1),
        "total_defects": report.total_defects,
        "matched_defects": sorted(list(report.matched_defects)),
        "matched_count": len(report.matched_defects),
        "unmatched_findings_count": len(report.unmatched_findings),
        "replay_rate": getattr(report, "replay_rate", 1.0),
        "precision": (len(report.matched_defects) / len(findings)) if findings else 1.0,
        "unsupported_findings": sum(1 for f in findings if not f.evidence),
        "is_held_out": is_held_out,
        "actions": 0,
        "tokens": 0,
    }
    trace_path = run_dir / "trace.jsonl"
    if trace_path.exists():
        actions_cnt = 0
        tokens_cnt = 0
        try:
            with open(trace_path, "r", encoding="utf-8") as tf:
                for line in tf:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if entry.get("event") == "tool_call":
                        actions_cnt += 1
                    tokens_cnt += entry.get("tokens", entry.get("total_tokens", 0))
            score_data["actions"] = actions_cnt
            score_data["tokens"] = tokens_cnt
        except Exception:
            pass
    with open(run_dir / "score.json", "w", encoding="utf-8") as sf:
        json.dump(score_data, sf, indent=2)


def handle_score(args: argparse.Namespace) -> int:
    from benchmark.scoring.harness import ScoringHarness
    from qa_cc.verdict.evidence import Finding

    run_dir = Path(args.run_dir)
    findings_path = run_dir / "findings.json"
    if not findings_path.exists():
        print(f"Error: {findings_path} does not exist in run directory.", file=sys.stderr)
        return 1

    with open(findings_path, "r", encoding="utf-8") as f:
        raw_findings = json.load(f)

    findings = [Finding.model_validate(rf) for rf in raw_findings]

    # Auto-detect target_type if not explicitly passed
    target_type = getattr(args, "target_type", None)
    if not target_type:
        trace_path = run_dir / "trace.jsonl"
        if trace_path.exists():
            try:
                with open(trace_path, "r", encoding="utf-8") as tf:
                    first_line = tf.readline()
                    if "localhost:3000" in first_line or "juice" in first_line.lower():
                        target_type = "juice_shop"
            except Exception:
                pass
        if not target_type:
            for f in findings:
                for ev in f.evidence:
                    url = ev.metadata.get("url", "")
                    content = str(ev.content)
                    if "localhost:3000" in url or "localhost:3000" in content or "juice-sh.op" in content:
                        target_type = "juice_shop"
                        break
                if target_type:
                    break
        if not target_type:
            target_type = "own_site"

    harness = ScoringHarness(args.ground_truth)

    if target_type == "juice_shop":
        from benchmark.scoring.juice_shop import JuiceShopScoreboardReader
        from benchmark.scoring.harness import _matches_juice_shop_challenge

        scoreboard_url = getattr(args, "scoreboard_url", "http://localhost:3000/api/Challenges")
        reader = JuiceShopScoreboardReader(base_url=scoreboard_url)
        challenges = reader.fetch_challenges()
        report = harness.score(
            findings=findings,
            target_type="juice_shop",
            scoreboard_challenges=challenges,
        )

        solved_challenges = [c for c in challenges if isinstance(c, dict) and c.get("solved") is True]
        matched_map = {}
        for finding in findings:
            for sc in solved_challenges:
                if _matches_juice_shop_challenge(finding, sc):
                    sc_name = sc.get("name", sc.get("key", "Unknown"))
                    matched_map[finding.id] = sc_name
                    break

        if args.compare:
            comp_dir = Path(args.compare)
            comp_findings_path = comp_dir / "findings.json"
            if not comp_findings_path.exists():
                print(f"Error: {comp_findings_path} does not exist in comparison run directory.", file=sys.stderr)
                return 1

            with open(comp_findings_path, "r", encoding="utf-8") as f:
                comp_raw = json.load(f)
            comp_findings = [Finding.model_validate(rf) for rf in comp_raw]
            report2 = harness.score(
                findings=comp_findings,
                target_type="juice_shop",
                scoreboard_challenges=challenges,
            )

            print("\n================== RUN COMPARISON (JUICE SHOP) ==================")
            print(f"Scoreboard API: {scoreboard_url}")
            print("-" * 52)
            print(f"{'Metric':<25} | {'Run 1':<12} | {'Run 2':<12}")
            print("-" * 52)
            print(f"{'Total Findings':<25} | {len(findings):<12} | {len(comp_findings):<12}")
            print(f"{'Matched Defects':<25} | {len(report.matched_defects):<12} | {len(report2.matched_defects):<12}")
            print(f"{'Recall':<25} | {report.recall*100:>11.1f}% | {report2.recall*100:>11.1f}%")
            print(f"{'Unmatched Findings':<25} | {len(report.unmatched_findings):<12} | {len(report2.unmatched_findings):<12}")
            print("-" * 52)
            print(f"Run 1 Matched: {sorted(list(report.matched_defects))}")
            print(f"Run 2 Matched: {sorted(list(report2.matched_defects))}")
            print("==================================================================")
            return 0

        print("================ JUICE SHOP SCORING REPORT ================")
        print(f"Target: OWASP Juice Shop")
        print(f"Scoreboard API: {scoreboard_url}")
        print(f"Total Challenges on Scoreboard: {report.total_defects}")
        print(f"Solved Challenges (Ground Truth): {report.matched_defects} ({len(report.matched_defects)})")
        print(f"Recall: {report.recall:.2%}")
        print(f"Run Findings Evaluated: {len(findings)}")
        print(f"Matched Findings: {len(findings) - len(report.unmatched_findings)}")
        for fid, cname in matched_map.items():
            print(f"  • {fid} verified against challenge: '{cname}'")
        print(f"Unmatched Findings (Precision Triage): {len(report.unmatched_findings)}")
        for uf in report.unmatched_findings:
            print(f"  • {uf.id}: {uf.summary}")
        print("===========================================================")
        _save_score_json(run_dir, target_type, report, findings, is_held_out=False)
        return 0

    report = harness.score(findings=findings, include_held_out=args.include_held_out)

    if args.compare:
        comp_dir = Path(args.compare)
        comp_findings_path = comp_dir / "findings.json"
        if not comp_findings_path.exists():
            print(f"Error: {comp_findings_path} does not exist in comparison run directory.", file=sys.stderr)
            return 1

        with open(comp_findings_path, "r", encoding="utf-8") as f:
            comp_raw = json.load(f)
        comp_findings = [Finding.model_validate(rf) for rf in comp_raw]
        report2 = harness.score(findings=comp_findings, include_held_out=args.include_held_out)

        print("\n================== RUN COMPARISON ==================")
        print(f"Ground Truth: {args.ground_truth}")
        print(f"Scope: {'All (including held-out)' if args.include_held_out else 'Tuning Set Only'}")
        print("-" * 52)
        print(f"{'Metric':<25} | {'Run 1 (Baseline)':<12} | {'Run 2 (Multi-Agent)':<12}")
        print("-" * 52)
        print(f"{'Total Findings':<25} | {len(findings):<12} | {len(comp_findings):<12}")
        print(f"{'Matched Defects':<25} | {len(report.matched_defects):<12} | {len(report2.matched_defects):<12}")
        print(f"{'Recall':<25} | {report.recall*100:>11.1f}% | {report2.recall*100:>11.1f}%")
        print(f"{'Unmatched Findings':<25} | {len(report.unmatched_findings):<12} | {len(report2.unmatched_findings):<12}")
        print("-" * 52)
        print(f"Run 1 Matched: {sorted(list(report.matched_defects))}")
        print(f"Run 2 Matched: {sorted(list(report2.matched_defects))}")
        print("====================================================")
        return 0

    print("================ SCORING REPORT ================")
    print(f"Ground Truth File: {args.ground_truth}")
    print(f"Set: {'All (including held-out)' if args.include_held_out else 'Tuning Set Only'}")
    print(f"Total Defects in Set: {report.total_defects}")
    print(f"Matched Defects: {report.matched_defects} ({len(report.matched_defects)})")
    print(f"Recall: {report.recall:.2%}")
    print(f"Unmatched Findings (Precision Triage): {len(report.unmatched_findings)}")
    print("================================================")
    _save_score_json(run_dir, target_type, report, findings, is_held_out=bool(getattr(args, "include_held_out", False)))
    return 0


def handle_results(args: argparse.Namespace) -> int:
    runs_dir = Path(getattr(args, "runs_dir", "runs"))
    if not runs_dir.exists():
        print("no scored runs found", file=sys.stderr)
        return 1

    score_files = list(runs_dir.glob("**/score.json"))
    if not score_files:
        print("no scored runs found", file=sys.stderr)
        return 1

    configs_data: Dict[str, List[Dict[str, Any]]] = {}
    for sf in score_files:
        try:
            with open(sf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        rel_parts = sf.relative_to(runs_dir).parts
        if len(rel_parts) >= 2:
            cfg_name = rel_parts[0]
        else:
            cfg_name = data.get("configuration", data.get("config", sf.parent.name))

        if cfg_name not in configs_data:
            configs_data[cfg_name] = []
        configs_data[cfg_name].append(data)

    if not configs_data:
        print("no scored runs found", file=sys.stderr)
        return 1

    aggregated = []
    include_held_out = getattr(args, "include_held_out", False)

    for cfg_name, runs in configs_data.items():
        is_held_out = any(r.get("is_held_out", False) for r in runs) or "held_out" in cfg_name.lower()
        if is_held_out and not include_held_out:
            continue

        n_runs = len(runs)
        recalls = []
        for r in runs:
            rec = r.get("recall", 0.0)
            if rec <= 1.0 and "recall_pct" not in r:
                recalls.append(rec * 100.0)
            else:
                recalls.append(r.get("recall_pct", rec * 100.0 if rec <= 1.0 else rec))

        avg_recall = sum(recalls) / n_runs if n_runs else 0.0
        if n_runs > 1:
            spread_val = (max(recalls) - min(recalls)) / 2.0
            recall_spread = f"±{spread_val:.1f}%"
        else:
            recall_spread = "N/A (single run)"

        total_defects = max((r.get("total_defects", 0) for r in runs), default=0)
        matched_counts = [len(r.get("matched_defects", [])) if "matched_defects" in r else r.get("matched_count", 0) for r in runs]
        avg_matched = sum(matched_counts) / n_runs if n_runs else 0
        recall_ratio = f"{int(round(avg_matched))}/{total_defects}" if total_defects else f"{int(round(avg_matched))}"

        replay_rates = []
        for r in runs:
            rr = r.get("replay_rate", r.get("replay_rate_pct", 0.0))
            if rr <= 1.0:
                rr *= 100.0
            replay_rates.append(rr)
        avg_replay = sum(replay_rates) / n_runs if n_runs else 0.0

        precisions = []
        for r in runs:
            p = r.get("precision", r.get("precision_pct", 1.0))
            if p <= 1.0:
                p *= 100.0
            precisions.append(p)
        avg_precision = sum(precisions) / n_runs if n_runs else 100.0

        unsupported = sum(r.get("unsupported_findings", 0) for r in runs)

        actions_list = [r.get("actions", r.get("avg_actions", 0)) for r in runs]
        avg_actions = sum(actions_list) / n_runs if n_runs else 0.0
        if n_runs > 1:
            act_spread = f"±{(max(actions_list) - min(actions_list)) / 2.0:.1f}"
        else:
            act_spread = "0"

        tokens_list = [r.get("tokens", r.get("avg_tokens", 0)) for r in runs]
        avg_tokens = int(sum(tokens_list) / n_runs) if n_runs else 0
        if n_runs > 1:
            tok_spread = f"±{int((max(tokens_list) - min(tokens_list)) / 2.0):,}"
        else:
            tok_spread = "0"

        all_matched = sorted(list({d for r in runs for d in r.get("matched_defects", [])}))
        scope = f"Tuning ({total_defects})" if not is_held_out else f"Held-Out ({total_defects})"

        aggregated.append({
            "name": cfg_name,
            "scope": scope,
            "runs": n_runs,
            "recall_pct": round(avg_recall, 1),
            "recall_ratio": recall_ratio,
            "recall_spread": recall_spread,
            "replay_rate_pct": round(avg_replay, 1),
            "precision_pct": round(avg_precision, 1),
            "unsupported_findings": unsupported,
            "avg_actions": round(avg_actions, 1),
            "actions_spread": act_spread,
            "avg_tokens": avg_tokens,
            "tokens_spread": tok_spread,
            "matched_defects": all_matched,
            "is_held_out": is_held_out,
        })

    if not aggregated:
        print("no scored runs found", file=sys.stderr)
        return 1

    if getattr(args, "format", "table") == "json":
        output = {
            "benchmark_results": aggregated,
            "include_held_out": include_held_out,
            "runs_evaluated": sum(c["runs"] for c in aggregated),
        }
        print(json.dumps(output, indent=2))
        return 0

    print("\n" + "=" * 105)
    print(" " * 36 + "BENCHMARK RESULTS SUMMARY")
    print("=" * 105)
    print(f"{'Configuration':<25} | {'Scope':<14} | {'Recall (Spread)':<20} | {'Replay':<8} | {'Precision':<9} | {'Actions':<8} | {'Tokens':<9}")
    print("-" * 105)
    for c in aggregated:
        rec_str = f"{c['recall_pct']:.1f}% ({c['recall_ratio']}) {c['recall_spread']}"
        print(
            f"{c['name']:<25} | {c['scope']:<14} | {rec_str:<20} | "
            f"{c['replay_rate_pct']:>6.1f}%  | {c['precision_pct']:>7.1f}%  | "
            f"{c['avg_actions']:>6.1f}   | {c['avg_tokens']:>8,}"
        )
    print("-" * 105)
    print(f"Total runs evaluated: {sum(c['runs'] for c in aggregated)}")
    print("=" * 105 + "\n")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "run":
        return handle_run(args)
    elif args.command == "score":
        return handle_score(args)
    elif args.command == "results":
        return handle_results(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
