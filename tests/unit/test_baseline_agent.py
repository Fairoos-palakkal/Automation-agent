"""Tests for BaselineAgent — Phase 1.6 (Red -> Green)."""
import tempfile
from pathlib import Path
import pytest

from qa_cc.agents.baseline import BaselineAgent, RunResult
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.trace.run_state import RunState
from qa_cc.trace.writer import TraceWriter
from qa_cc.verdict.evidence import EvidenceType


def make_tool_response(tool_name: str, args: dict, content: str = ""):
    return {
        "id": "call-1",
        "model": "fake-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": args,
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def make_text_response(text: str):
    return {
        "id": "call-text",
        "model": "fake-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": text,
                    "tool_calls": None,
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


class TestBaselineAgent:
    def test_baseline_agent_produces_findings(self):
        """Baseline agent guided by LLM finds a defect and reports >= 1 Finding with Evidence."""
        provider = FakeProvider(
            responses=[
                # Turn 1: navigate to catalog
                make_tool_response("navigate", {"url": "http://localhost:3000/catalog.html"}),
                # Turn 2: report finding
                make_tool_response(
                    "report_finding",
                    {
                        "summary": "Catalog filter throws TypeError",
                        "evidence_type": "console_log",
                        "evidence_content": "TypeError: Cannot read properties of undefined",
                    },
                ),
                # Turn 3: finish run
                make_tool_response("finish", {"summary": "Exploration complete"}),
            ]
        )
        client = LLMClient(provider=provider)
        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(name="navigate", handler=lambda url: {"url": url, "snapshot": "<html>Catalog</html>"}, is_url_action=True))

        agent = BaselineAgent(llm_client=client, gateway=gateway)
        result = agent.run(objective="Explore catalog for errors", target="http://localhost:3000/catalog.html")

        assert isinstance(result, RunResult)
        assert len(result.findings) >= 1
        finding = result.findings[0]
        assert "TypeError" in finding.summary
        assert len(finding.evidence) >= 1
        assert finding.evidence[0].type == EvidenceType.CONSOLE_LOG

    def test_baseline_agent_stops_on_budget(self):
        """Baseline agent terminates cleanly when action budget is exceeded."""
        # Provider that loops forever with navigate
        infinite_responses = [
            make_tool_response("navigate", {"url": "http://localhost:3000/page"}) for _ in range(10)
        ]
        provider = FakeProvider(responses=infinite_responses)
        client = LLMClient(provider=provider)
        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(name="navigate", handler=lambda url: {"url": url, "snapshot": "html"}, is_url_action=True))

        run_state = RunState(max_actions=2)
        agent = BaselineAgent(llm_client=client, gateway=gateway, run_state=run_state)
        result = agent.run(objective="Test budget limit", target="http://localhost:3000")

        assert result.budget_exceeded is True
        assert run_state.actions_count == 2

    def test_baseline_agent_captures_evidence(self):
        """Every Finding produced by BaselineAgent has non-empty Evidence."""
        provider = FakeProvider(
            responses=[
                make_tool_response(
                    "report_finding",
                    {
                        "summary": "Missing alt tag",
                        "evidence_type": "dom_snapshot",
                        "evidence_content": "<img src='logo.png'>",
                    },
                ),
                make_tool_response("finish", {"summary": "Done"}),
            ]
        )
        client = LLMClient(provider=provider)
        gateway = ToolGateway()

        agent = BaselineAgent(llm_client=client, gateway=gateway)
        result = agent.run(objective="Accessibility check", target="http://localhost:3000")

        for f in result.findings:
            assert len(f.evidence) > 0
            assert f.evidence[0].content

    def test_baseline_agent_writes_trace(self):
        """Running BaselineAgent logs entries into the JSONL trace file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "agent_trace.jsonl"
            trace_writer = TraceWriter(trace_path)

            provider = FakeProvider(
                responses=[
                    make_tool_response("finish", {"summary": "Done"}),
                ]
            )
            client = LLMClient(provider=provider)
            gateway = ToolGateway(trace_writer=trace_writer)

            agent = BaselineAgent(
                llm_client=client,
                gateway=gateway,
                trace_writer=trace_writer,
            )
            agent.run(objective="Trace test", target="http://localhost:3000")

            assert trace_path.exists()
            entries = trace_writer.read_entries()
            assert len(entries) >= 1

    def test_baseline_agent_loop_recovery(self):
        """When an agent gets stuck repeating actions, loop detector triggers recovery."""
        repeated_responses = [
            make_tool_response("click", {"selector": "#stuck-btn"}),
            make_tool_response("click", {"selector": "#stuck-btn"}),
            make_tool_response("click", {"selector": "#stuck-btn"}),
            make_tool_response("click", {"selector": "#stuck-btn"}),
            make_tool_response("click", {"selector": "#stuck-btn"}),
            make_tool_response("finish", {"summary": "Aborted"}),
        ]
        provider = FakeProvider(responses=repeated_responses)
        client = LLMClient(provider=provider)
        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(name="click", handler=lambda selector: {"snapshot": "same"}))

        agent = BaselineAgent(llm_client=client, gateway=gateway)
        result = agent.run(objective="Loop recovery test", target="http://localhost:3000")

        assert result.loop_recovery_triggered is True
