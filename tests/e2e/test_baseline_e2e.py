"""End-to-end test for Baseline Agent against Own Site — Phase 1.10.

Marked @pytest.mark.e2e — excluded from the default test run.
Run explicitly with: pytest tests/e2e/ -v -m e2e
"""
import functools
import http.server
import os
from pathlib import Path
import socketserver
import tempfile
import threading
import pytest

from benchmark.scoring.harness import ScoringHarness
from qa_cc.agents.baseline import BaselineAgent
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.report.generator import generate_report
from qa_cc.tools.browser import BrowserTools
from qa_cc.tools.playwright_driver import PlaywrightPageDriver
from qa_cc.trace.run_state import RunState
from qa_cc.trace.writer import TraceWriter

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="module")
def own_site_server():
    """Serves benchmark/own_site over a local HTTP server on an available port."""
    directory = str(REPO_ROOT / "benchmark" / "own_site")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)

    # Bind to port 0 for an ephemeral available port
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        yield f"http://127.0.0.1:{port}"
        httpd.shutdown()


@pytest.mark.e2e
class TestBaselineE2E:
    def test_e2e_baseline_run_on_own_site(self, own_site_server, tmp_path):
        """Playwright + BaselineAgent run against Own Site produces Findings with Evidence."""
        from playwright.sync_api import sync_playwright

        trace_file = tmp_path / "e2e_trace.jsonl"
        report_file = tmp_path / "e2e_report.html"
        screenshot_file = tmp_path / "e2e_shot.png"

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

            # Register live browser tools into the gateway
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
                    name="screenshot",
                    handler=lambda path=str(screenshot_file): browser_tools.screenshot(path),
                )
            )

            # Scripted FakeProvider directing exploration of catalog error
            catalog_url = f"{own_site_server}/catalog.html"
            provider = FakeProvider(
                responses=[
                    # Step 1: Navigate to catalog
                    {
                        "id": "e2e-1",
                        "model": "bench-model",
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": "tc1",
                                            "type": "function",
                                            "function": {
                                                "name": "navigate",
                                                "arguments": {"url": catalog_url},
                                            },
                                        }
                                    ],
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 50, "completion_tokens": 15, "total_tokens": 65},
                    },
                    # Step 2: Click filter button to trigger catalog defect
                    {
                        "id": "e2e-2",
                        "model": "bench-model",
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": "tc2",
                                            "type": "function",
                                            "function": {
                                                "name": "click",
                                                "arguments": {"selector": "#filter-btn"},
                                            },
                                        }
                                    ],
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 40, "completion_tokens": 15, "total_tokens": 55},
                    },
                    # Step 3: Take screenshot
                    {
                        "id": "e2e-3",
                        "model": "bench-model",
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": "tc3",
                                            "type": "function",
                                            "function": {
                                                "name": "screenshot",
                                                "arguments": {"path": str(screenshot_file)},
                                            },
                                        }
                                    ],
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
                    },
                    # Step 4: Report finding
                    {
                        "id": "e2e-4",
                        "model": "bench-model",
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": "tc4",
                                            "type": "function",
                                            "function": {
                                                "name": "report_finding",
                                                "arguments": {
                                                    "summary": "Catalog filter throws uncaught TypeError",
                                                    "evidence_type": "screenshot",
                                                    "evidence_content": str(screenshot_file),
                                                },
                                            },
                                        }
                                    ],
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 40, "completion_tokens": 20, "total_tokens": 60},
                    },
                    # Step 5: Finish
                    {
                        "id": "e2e-5",
                        "model": "bench-model",
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": "tc5",
                                            "type": "function",
                                            "function": {
                                                "name": "finish",
                                                "arguments": {"summary": "Completed catalog testing"},
                                            },
                                        }
                                    ],
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    },
                ]
            )

            client = LLMClient(provider=provider)
            run_state = RunState(max_actions=25)
            agent = BaselineAgent(
                llm_client=client,
                gateway=gateway,
                run_state=run_state,
                trace_writer=trace_writer,
            )

            result = agent.run(
                objective="Explore catalog page and verify button handlers",
                target=catalog_url,
            )

            # Verification 1: Findings produced with evidence
            assert len(result.findings) >= 1
            finding = result.findings[0]
            assert "Catalog filter" in finding.summary
            assert len(finding.evidence) >= 1
            assert screenshot_file.exists()

            # Verification 2: Static HTML report generated
            generate_report(result, report_file)
            assert report_file.exists()
            content = report_file.read_text(encoding="utf-8")
            assert "Catalog filter throws uncaught TypeError" in content

            # Verification 3: Scoring against tuning set yields positive recall
            gt_path = REPO_ROOT / "benchmark" / "ground_truth" / "defects.json"
            harness = ScoringHarness(gt_path)
            score_report = harness.score(result.findings, include_held_out=False)

            assert "DEFECT-003" in score_report.matched_defects
            assert score_report.recall > 0.0

            browser.close()
