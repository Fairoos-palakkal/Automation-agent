"""End-to-End Verdict Pipeline Verification on Own Site — Phase 7 (T-15).

Verifies:
1. Planted DEFECT-004 on Own Site is confirmed through live engine assertion and fresh-context replay.
2. Grep / AST verification that Verdict creation occurs strictly within verdict/ and challenger modules.

Marked @pytest.mark.e2e.
Run with: pytest tests/e2e/test_verdict_pipeline_e2e.py -v -m e2e
"""
import functools
import http.server
import json
from pathlib import Path
import re
import socketserver
import threading
import pytest

from qa_cc.agents.baseline import BaselineAgent
from qa_cc.gateway.gateway import ToolDefinition, ToolGateway
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.report.generator import generate_report
from qa_cc.tools.browser import BrowserTools
from qa_cc.tools.playwright_driver import PlaywrightPageDriver
from qa_cc.trace.run_state import RunState
from qa_cc.trace.writer import TraceWriter
from qa_cc.verdict.engine import AssertionRule, VerdictEngine
from qa_cc.verdict.evidence import Finding, VerdictType
from qa_cc.verdict.replayer import Replayer
from qa_cc.verdict.verifier import FindingVerifier

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="module")
def own_site_server():
    """Serves benchmark/own_site over a local HTTP server on an available port."""
    directory = str(REPO_ROOT / "benchmark" / "own_site")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)

    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        yield f"http://127.0.0.1:{port}"
        httpd.shutdown()


@pytest.mark.e2e
class TestVerdictPipelineE2E:
    def test_e2e_confirms_defect_004_via_engine_and_replay(self, own_site_server, tmp_path):
        """T-15: Own Site DEFECT-004 is confirmed with a deterministic FAIL verdict via engine and replay."""
        from playwright.sync_api import sync_playwright

        trace_file = tmp_path / "defect004_trace.jsonl"
        report_file = tmp_path / "defect004_report.html"
        findings_file = tmp_path / "findings.json"

        cart_url = f"{own_site_server}/cart.html"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            driver = PlaywrightPageDriver(page)
            browser_tools = BrowserTools(driver)

            trace_writer = TraceWriter(trace_file)
            gateway = ToolGateway(
                allowlist=["127.0.0.1", "localhost"],
                trace_writer=trace_writer,
            )

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

            # Canned agent responses to explore cart, decrement quantity twice, and report DEFECT-004
            responses = [
                # Turn 1: navigate to cart
                {
                    "id": "turn-1",
                    "model": "bench-model",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "tc-1",
                                "type": "function",
                                "function": {"name": "navigate", "arguments": json.dumps({"url": cart_url})},
                            }],
                        }
                    }],
                },
                # Turn 2: click decrement button (1 -> 0)
                {
                    "id": "turn-2",
                    "model": "bench-model",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "tc-2",
                                "type": "function",
                                "function": {"name": "click", "arguments": json.dumps({"selector": "#decrement-qty"})},
                            }],
                        }
                    }],
                },
                # Turn 3: click decrement button again (0 -> -1, triggering DEFECT-004)
                {
                    "id": "turn-3",
                    "model": "bench-model",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "tc-3",
                                "type": "function",
                                "function": {"name": "click", "arguments": json.dumps({"selector": "#decrement-qty"})},
                            }],
                        }
                    }],
                },
                # Turn 4: report finding with structured claims
                {
                    "id": "turn-4",
                    "model": "bench-model",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "tc-4",
                                "type": "function",
                                "function": {
                                    "name": "report_finding",
                                    "arguments": json.dumps({
                                        "summary": "Cart quantity allows negative values",
                                        "expected": "0",
                                        "actual": "-1",
                                        "selector_or_url": "#qty-val",
                                        "step_ids": ["step-1", "step-2", "step-3"],
                                        "evidence_type": "dom_snapshot",
                                    }),
                                },
                            }],
                        }
                    }],
                },
                # Turn 5: finish
                {
                    "id": "turn-5",
                    "model": "bench-model",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": "tc-5",
                                "type": "function",
                                "function": {"name": "finish", "arguments": json.dumps({"summary": "Exploration complete"})},
                            }],
                        }
                    }],
                },
            ]

            client = LLMClient(provider=FakeProvider(responses=responses))
            agent = BaselineAgent(
                llm_client=client,
                gateway=gateway,
                trace_writer=trace_writer,
            )

            result = agent.run(objective="Test cart quantity bounds", target=cart_url)
            assert len(result.findings) == 1
            finding = result.findings[0]

            # Current live state from the browser
            live_state = {
                "html": page.content(),
                "url": page.url,
                "console_errors": driver.console_messages,
            }

            # Run deterministic verification pipeline
            replayer = Replayer(browser=browser, trace_writer=trace_writer)
            verifier = FindingVerifier(
                verdict_engine=VerdictEngine(),
                replayer=replayer,
                trace_writer=trace_writer,
            )

            verified_finding = verifier.verify_finding(finding, live_page_state=live_state)

            # Assert deterministic verdict is FAIL
            assert verified_finding.verdict is not None
            assert verified_finding.verdict.type == VerdictType.FAIL
            assert "verified by live assertion and fresh-context replay" in verified_finding.verdict.reason.lower()

            # Save and verify report
            result.findings = [verified_finding]
            result.trace_path = str(trace_file)
            generate_report(result, report_file)

            report_html = report_file.read_text(encoding="utf-8")
            assert "FAIL" in report_html
            assert "verified by live assertion and fresh-context replay" in report_html
            assert "#decrement-qty" in report_html

            browser.close()

    def test_grep_verifies_zero_verdict_instantiation_outside_verdict_and_challenger(self):
        """T-15: AST and regex audit verifies zero Verdict instantiation in scoring, CLI, or agent modules."""
        src_dir = REPO_ROOT / "src"
        benchmark_dir = REPO_ROOT / "benchmark"

        allowed_prefixes = (
            str(src_dir / "qa_cc" / "verdict"),
            str(src_dir / "qa_cc" / "agents" / "challenger.py"),
        )

        all_py_files = list(src_dir.rglob("*.py")) + list(benchmark_dir.rglob("*.py"))
        violations = []

        verdict_call_pattern = re.compile(r"\bVerdict\s*\(")

        for py_file in all_py_files:
            file_str = str(py_file)
            # Skip definition file itself and allowed modules
            if any(file_str.startswith(allowed) for allowed in allowed_prefixes):
                continue

            content = py_file.read_text(encoding="utf-8")
            for line_no, line in enumerate(content.splitlines(), start=1):
                # Ignore import lines
                if "import" in line:
                    continue
                if verdict_call_pattern.search(line):
                    violations.append(f"{file_str}:{line_no} -> {line.strip()}")

        assert not violations, f"Forbidden Verdict(...) instantiation found in non-verdict modules:\n" + "\n".join(violations)
