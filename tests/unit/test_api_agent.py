"""Tests for APIAgent and HTTP tool — Phase 2.4 (Red → Green)."""
import pytest

from qa_cc.agents.api import APIAgent
from qa_cc.agents.browser import TaskResult
from qa_cc.agents.plan import Task, AgentType
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition, TargetNotAllowed
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.tools.http import HttpTool
from qa_cc.verdict.evidence import EvidenceType


def make_tool_response(tool_name: str, args: dict, content: str = ""):
    return {
        "id": "call-api",
        "model": "fake-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": "tc-api-1",
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
        "usage": {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
    }


class TestApiAgentAndHttpTool:
    def test_http_tool_enforces_allowlist(self):
        """HTTP tool registered in ToolGateway raises TargetNotAllowed for non-allowlisted URLs."""
        http_tool = HttpTool()
        gateway = ToolGateway(allowlist=["localhost", "127.0.0.1"])
        gateway.register_tool(ToolDefinition(
            name="http_request",
            handler=http_tool.request,
            is_url_action=True,
        ))

        with pytest.raises(TargetNotAllowed):
            gateway.execute("http_request", {"method": "GET", "url": "https://unauthorized-domain.com/api"})

    def test_http_tool_records_evidence(self):
        """HTTP tool request/response pair can be captured as Evidence."""
        # Using a mock handler in HttpTool or mock response
        class MockResponse:
            status_code = 200
            text = '{"status": "ok"}'
            headers = {"content-type": "application/json"}
            def json(self):
                return {"status": "ok"}

        http_tool = HttpTool(requester=lambda **kwargs: MockResponse())
        res = http_tool.request(method="GET", url="http://localhost:3000/api/items")

        assert res["status_code"] == 200
        assert "evidence" in res
        evidence = res["evidence"]
        assert evidence.type == EvidenceType.NETWORK_REQUEST
        assert "200" in evidence.content
        assert "http://localhost:3000/api/items" in evidence.content

    def test_api_agent_uses_http_tools_only(self):
        """APIAgent tool set contains only HTTP tool and control tools, no browser tools."""
        client = LLMClient(provider=FakeProvider(responses=[]))
        gateway = ToolGateway()

        agent = APIAgent(llm_client=client, gateway=gateway)
        tool_names = [t["function"]["name"] for t in agent.tools]

        assert "http_request" in tool_names
        assert "report_finding" in tool_names
        assert "finish" in tool_names
        # Browser tools must not be present
        assert "navigate" not in tool_names
        assert "click" not in tool_names
        assert "fill" not in tool_names
        assert "screenshot" not in tool_names

    def test_api_agent_returns_findings(self):
        """FakeProvider-scripted API exploration returns Findings with Evidence."""
        task = Task(
            id="task-api-1",
            goal="Test API endpoint for 500 error",
            assignee=AgentType.API,
            budget={"max_actions": 5, "max_tokens": 5000},
        )

        provider = FakeProvider(responses=[
            make_tool_response(
                "http_request",
                {"method": "POST", "url": "http://localhost:3000/api/cart", "body": "invalid"},
            ),
            make_tool_response(
                "report_finding",
                {
                    "summary": "POST /api/cart returns unhandled 500 Internal Server Error",
                    "evidence_type": "network_request",
                    "evidence_content": "POST /api/cart -> 500 Internal Server Error",
                },
            ),
            make_tool_response("finish", {"summary": "Completed API test"}),
        ])
        client = LLMClient(provider=provider)
        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(
            name="http_request",
            handler=lambda method, url, **kwargs: {"status_code": 500, "body": "Internal Server Error"},
            is_url_action=True,
        ))

        agent = APIAgent(llm_client=client, gateway=gateway)
        result = agent.execute(task, base_url="http://localhost:3000")

        assert isinstance(result, TaskResult)
        assert len(result.findings) == 1
        finding = result.findings[0]
        assert "500" in finding.summary
        assert finding.evidence[0].type == EvidenceType.NETWORK_REQUEST

    def test_api_agent_respects_task_budget(self):
        """APIAgent stops execution cleanly when its Task budget is reached."""
        task = Task(
            id="task-api-budget",
            goal="Send requests repeatedly until budget limit",
            assignee=AgentType.API,
            budget={"max_actions": 2, "max_tokens": 5000},
        )

        loop_responses = [
            make_tool_response("http_request", {"method": "GET", "url": "http://localhost:3000/api/1"}),
            make_tool_response("http_request", {"method": "GET", "url": "http://localhost:3000/api/2"}),
            make_tool_response("http_request", {"method": "GET", "url": "http://localhost:3000/api/3"}),
        ]
        provider = FakeProvider(responses=loop_responses)
        client = LLMClient(provider=provider)
        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(
            name="http_request",
            handler=lambda method, url, **kwargs: {"status_code": 200, "body": "{}"},
            is_url_action=True,
        ))

        agent = APIAgent(llm_client=client, gateway=gateway)
        result = agent.execute(task, base_url="http://localhost:3000")

        assert result.budget_exceeded is True
        assert result.actions_count == 2

    def test_api_agent_http_request_with_tracewriter_serializes_evidence(self, tmp_path):
        """HTTP tool returning Evidence does not crash ToolGateway or TraceWriter serialization."""
        from qa_cc.trace.writer import TraceWriter

        trace_file = tmp_path / "trace.jsonl"
        trace_writer = TraceWriter(trace_file)

        class MockResp:
            status_code = 200
            text = '{"status":"ok"}'
            headers = {"content-type": "application/json"}

        http_tool = HttpTool(requester=lambda **kwargs: MockResp())
        gateway = ToolGateway(trace_writer=trace_writer)
        gateway.register_tool(ToolDefinition(
            name="http_request",
            handler=http_tool.request,
            is_url_action=True,
        ))

        provider = FakeProvider(responses=[
            make_tool_response("http_request", {"method": "GET", "url": "http://localhost:3000/api/status"}),
            make_tool_response("finish", {"summary": "Done"}),
        ])
        client = LLMClient(provider=provider)
        agent = APIAgent(llm_client=client, gateway=gateway, trace_writer=trace_writer)
        task = Task(
            id="task-test-serialize",
            goal="Test serialization",
            assignee=AgentType.API,
            budget={"max_actions": 5, "max_tokens": 5000},
        )

        result = agent.execute(task, base_url="http://localhost:3000")
        assert result.status == "completed"
        entries = trace_writer.read_entries()
        tool_entries = [e for e in entries if e.get("type") == "tool_call"]
        assert len(tool_entries) == 1
        assert tool_entries[0]["tool_name"] == "http_request"
        assert tool_entries[0]["result"]["status_code"] == 200
