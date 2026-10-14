"""End-to-end test for Multi-Agent Orchestrator against Own Site — Phase 2 Gate.

Marked @pytest.mark.e2e — excluded from default test run.
Run explicitly with: pytest tests/e2e/test_multi_agent_e2e.py -v -m e2e
"""
import functools
import http.server
import json
from pathlib import Path
import socketserver
import threading
import pytest
from starlette.testclient import TestClient

from benchmark.scoring.harness import ScoringHarness
from qa_cc.agents.api import APIAgent
from qa_cc.agents.browser import BrowserAgent
from qa_cc.agents.orchestrator import Orchestrator
from qa_cc.agents.plan import Plan, Task, AgentType
from qa_cc.agents.planner import Planner
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.report.generator import generate_report
from qa_cc.tools.browser import BrowserTools
from qa_cc.tools.http import HttpTool
from qa_cc.tools.mock_api import app as fastapi_app
from qa_cc.tools.playwright_driver import PlaywrightPageDriver
from qa_cc.trace.run_state import RunState
from qa_cc.trace.writer import TraceWriter


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
class TestMultiAgentE2E:
    def test_e2e_multi_agent_run_on_own_site(self, own_site_server, tmp_path):
        """Planner + BrowserAgent + APIAgent coordinated by Orchestrator on Own Site."""
        from playwright.sync_api import sync_playwright

        trace_file = tmp_path / "multi_agent_trace.jsonl"
        report_file = tmp_path / "multi_agent_report.html"
        screenshot_file = tmp_path / "multi_agent_shot.png"

        catalog_url = f"{own_site_server}/catalog.html"

        # 1. Planner FakeProvider
        plan_data = {
            "objective": "Verify catalog and contact endpoints",
            "tasks": [
                {
                    "id": "task-browser",
                    "goal": "Test catalog filter button",
                    "assignee": "browser",
                    "budget": {"max_actions": 5, "max_tokens": 5000},
                },
                {
                    "id": "task-api",
                    "goal": "Test contact submission API endpoint",
                    "assignee": "api",
                    "budget": {"max_actions": 5, "max_tokens": 5000},
                },
            ],
        }
        planner_provider = FakeProvider(responses=[
            {
                "id": "planner-call",
                "model": "bench-model",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(plan_data),
                            "tool_calls": None,
                        }
                    }
                ],
                "usage": {"prompt_tokens": 30, "completion_tokens": 40, "total_tokens": 70},
            }
        ])
        planner_client = LLMClient(provider=planner_provider)
        planner = Planner(llm_client=planner_client)

        # 2. BrowserAgent FakeProvider
        browser_provider = FakeProvider(responses=[
            # Navigate to catalog
            {
                "id": "b-1",
                "model": "bench-model",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "btc-1",
                            "type": "function",
                            "function": {"name": "navigate", "arguments": {"url": catalog_url}},
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
            },
            # Click filter button
            {
                "id": "b-2",
                "model": "bench-model",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "btc-2",
                            "type": "function",
                            "function": {"name": "click", "arguments": {"selector": "#filter-btn"}},
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
            },
            # Screenshot
            {
                "id": "b-3",
                "model": "bench-model",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "btc-3",
                            "type": "function",
                            "function": {"name": "screenshot", "arguments": {"path": str(screenshot_file)}},
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            },
            # Report finding (DEFECT-003)
            {
                "id": "b-4",
                "model": "bench-model",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "btc-4",
                            "type": "function",
                            "function": {
                                "name": "report_finding",
                                "arguments": {
                                    "summary": "Catalog filter throws TypeError on catalog page",
                                    "evidence_type": "screenshot",
                                    "evidence_content": str(screenshot_file),
                                },
                            },
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45},
            },
            # Finish
            {
                "id": "b-5",
                "model": "bench-model",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "btc-5",
                            "type": "function",
                            "function": {"name": "finish", "arguments": {"summary": "Browser test complete"}},
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        ])
        browser_client = LLMClient(provider=browser_provider)

        # 3. APIAgent FakeProvider
        api_provider = FakeProvider(responses=[
            # Send HTTP request to /api/contact with invalid email
            {
                "id": "a-1",
                "model": "bench-model",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "atc-1",
                            "type": "function",
                            "function": {
                                "name": "http_request",
                                "arguments": {
                                    "method": "POST",
                                    "url": "http://127.0.0.1:8000/api/contact",
                                    "body": json.dumps({"name": "Bob", "email": "bademail"}),
                                },
                            },
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45},
            },
            # Report finding (DEFECT-001: Missing email validation on contact form)
            {
                "id": "a-2",
                "model": "bench-model",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "atc-2",
                            "type": "function",
                            "function": {
                                "name": "report_finding",
                                "arguments": {
                                    "summary": "Missing email validation on contact form allows invalid email",
                                    "evidence_type": "network_request",
                                    "evidence_content": "POST /api/contact -> 200 with invalid email accepted",
                                },
                            },
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45},
            },
            # Finish
            {
                "id": "a-3",
                "model": "bench-model",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "atc-3",
                            "type": "function",
                            "function": {"name": "finish", "arguments": {"summary": "API test complete"}},
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        ])
        api_client = LLMClient(provider=api_provider)

        # 4. Playwright & Gateway setup
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

            # Register browser tools
            gateway.register_tool(ToolDefinition(
                name="navigate",
                handler=browser_tools.navigate,
                is_url_action=True,
            ))
            gateway.register_tool(ToolDefinition(
                name="click",
                handler=browser_tools.click,
            ))
            gateway.register_tool(ToolDefinition(
                name="screenshot",
                handler=lambda path=str(screenshot_file): browser_tools.screenshot(path),
            ))

            # Register HTTP tool routing to mock FastAPI backend via starlette TestClient
            test_client = TestClient(fastapi_app)

            def mock_requester(method: str, url: str, headers: dict = None, body: any = None):
                # Map url path to FastAPI app
                from urllib.parse import urlparse
                path = urlparse(url).path
                json_data = json.loads(body) if isinstance(body, str) and body.startswith("{") else None
                if method == "POST":
                    return test_client.post(path, json=json_data)
                elif method == "GET":
                    return test_client.get(path)
                return test_client.request(method, path, json=json_data)

            http_tool = HttpTool(requester=mock_requester)
            gateway.register_tool(ToolDefinition(
                name="http_request",
                handler=http_tool.request,
                is_url_action=True,
            ))

            browser_agent = BrowserAgent(llm_client=browser_client, gateway=gateway, trace_writer=trace_writer)
            api_agent = APIAgent(llm_client=api_client, gateway=gateway, trace_writer=trace_writer)

            orchestrator = Orchestrator(
                planner=planner,
                browser_agent=browser_agent,
                api_agent=api_agent,
                trace_writer=trace_writer,
            )

            result = orchestrator.run(
                objective="Full multi-agent exploration: catalog UI and contact API",
                target=f"{own_site_server}/index.html",
            )

            # Verification 1: Both sub-agents produced findings
            assert len(result.findings) >= 2
            summaries = [f.summary for f in result.findings]
            assert any("Catalog" in s for s in summaries)
            assert any("email" in s.lower() for s in summaries)

            # Verification 2: Trace and HTML report generated
            assert trace_file.exists()
            generate_report(result, report_file)
            assert report_file.exists()

            # Verification 3: Scoring against tuning set yields positive recall for DEFECT-001 and DEFECT-003
            gt_path = REPO_ROOT / "benchmark" / "ground_truth" / "defects.json"
            harness = ScoringHarness(gt_path)
            score_report = harness.score(result.findings, include_held_out=False)

            assert "DEFECT-001" in score_report.matched_defects
            assert "DEFECT-003" in score_report.matched_defects
            assert score_report.recall >= 0.4  # At least 2 of 5 tuning defects matched

            browser.close()
