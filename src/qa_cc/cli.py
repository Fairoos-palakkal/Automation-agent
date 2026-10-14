import argparse
import json
import os
from pathlib import Path
import sys
from typing import List, Optional

from qa_cc.agents.baseline import BaselineAgent, RunResult
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.report.generator import generate_report
from qa_cc.trace.run_state import RunState
from qa_cc.trace.writer import TraceWriter
from qa_cc.verdict.evidence import Evidence, EvidenceType, Finding


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
    run_parser.add_argument("--output-dir", default="./run_output", help="Directory for trace and reports")
    run_parser.add_argument("--mock", action="store_true", help="Use deterministic mock provider for testing")
    run_parser.add_argument("--max-actions", type=int, default=25, help="Action budget limit")

    # Score subcommand
    score_parser = subparsers.add_parser("score", help="Score findings from a completed run against ground truth")
    score_parser.add_argument("--run-dir", required=True, help="Directory containing run artifacts")
    score_parser.add_argument("--ground-truth", default="benchmark/ground_truth/defects.json", help="Path to ground truth defects.json")
    score_parser.add_argument("--include-held-out", action="store_true", help="Include held-out evaluation defects")

    return parser


def handle_run(args: argparse.Namespace) -> int:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.jsonl"
    report_path = out_dir / "report.html"

    trace_writer = TraceWriter(trace_path)
    run_state = RunState(max_actions=args.max_actions)
    gateway = ToolGateway(trace_writer=trace_writer)

    browser_instance = None
    playwright_ctx = None

    if args.mock:
        # Scripted canned responses for mock mode
        canned = [
            {
                "id": "canned-1",
                "model": "fake-canned",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
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
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
            {
                "id": "canned-2",
                "model": "fake-canned",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "c2",
                                    "type": "function",
                                    "function": {"name": "finish", "arguments": {"summary": "Done"}},
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            },
        ]
        provider = FakeProvider(responses=canned)
        client = LLMClient(provider=provider)
    else:
        api_key = os.environ.get("LLM_API_KEY", "")
        if api_key and api_key != "your_api_key_here":
            from qa_cc.llm.openai_provider import OpenAICompatibleProvider
            provider = OpenAICompatibleProvider(
                base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
                api_key=api_key,
                model=os.environ.get("LLM_MODEL", "Qwen3.8-Flash"),
            )
        else:
            provider = FakeProvider()
        client = LLMClient(provider=provider)

        # Wire live Playwright browser
        try:
            from playwright.sync_api import sync_playwright
            from qa_cc.tools.playwright_driver import PlaywrightPageDriver
            from qa_cc.tools.browser import BrowserTools

            playwright_ctx = sync_playwright().start()
            browser_instance = playwright_ctx.chromium.launch(headless=True)
            page = browser_instance.new_page()
            driver = PlaywrightPageDriver(page)
            browser_tools = BrowserTools(driver)

            gateway.register_tool(
                ToolDefinition(
                    name="navigate",
                    handler=browser_tools.navigate,
                    is_url_action=True,
                )
            )
            gateway.register_tool(
                ToolDefinition(
                    name="click",
                    handler=browser_tools.click,
                )
            )
            gateway.register_tool(
                ToolDefinition(
                    name="fill",
                    handler=browser_tools.fill,
                )
            )
            gateway.register_tool(
                ToolDefinition(
                    name="screenshot",
                    handler=lambda path=str(out_dir / "screenshot.png"): browser_tools.screenshot(path),
                )
            )
        except Exception as e:
            print(f"Note: Running without live browser ({e})")

    agent = BaselineAgent(
        llm_client=client,
        gateway=gateway,
        run_state=run_state,
        trace_writer=trace_writer,
    )
    result = agent.run(objective=args.objective, target=args.target)

    if browser_instance:
        browser_instance.close()
    if playwright_ctx:
        playwright_ctx.stop()

    # Save findings JSON
    findings_path = out_dir / "findings.json"
    with open(findings_path, "w", encoding="utf-8") as f:
        json.dump([finding.model_dump() for finding in result.findings], f, indent=2)

    generate_report(result, report_path)
    print(f"Run completed. Actions: {result.actions_count}, Findings: {len(result.findings)}")
    print(f"Trace saved to {trace_path}")
    print(f"Findings saved to {findings_path}")
    print(f"Report saved to {report_path}")
    return 0


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
    harness = ScoringHarness(args.ground_truth)
    report = harness.score(findings=findings, include_held_out=args.include_held_out)

    print("================ SCORING REPORT ================")
    print(f"Ground Truth File: {args.ground_truth}")
    print(f"Set: {'All (including held-out)' if args.include_held_out else 'Tuning Set Only'}")
    print(f"Total Defects in Set: {report.total_defects}")
    print(f"Matched Defects: {report.matched_defects} ({len(report.matched_defects)})")
    print(f"Recall: {report.recall:.2%}")
    print(f"Unmatched Findings (Precision Triage): {len(report.unmatched_findings)}")
    print("================================================")
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
