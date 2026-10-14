"""Tests for BrowserAgent — Phase 2.3 (Red → Green)."""
import pytest

from qa_cc.agents.browser import BrowserAgent, TaskResult
from qa_cc.agents.plan import Task, AgentType
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.verdict.evidence import EvidenceType


def make_tool_response(tool_name: str, args: dict, content: str = ""):
    return {
        "id": "call-browser",
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
        "usage": {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
    }


class TestBrowserAgent:
    def test_browser_agent_receives_only_task(self):
        """BrowserAgent context contains only its Task goal and target, not full orchestrator history."""
        task = Task(
            id="task-browser-1",
            goal="Verify checkout page fields",
            assignee=AgentType.BROWSER,
            budget={"max_actions": 5, "max_tokens": 5000},
        )

        provider = FakeProvider(responses=[
            make_tool_response("finish", {"summary": "Done inspecting fields"}),
        ])
        client = LLMClient(provider=provider)
        gateway = ToolGateway()

        agent = BrowserAgent(llm_client=client, gateway=gateway)
        result = agent.execute(task, target_url="http://localhost:3000/checkout.html")

        assert isinstance(result, TaskResult)
        assert len(provider.calls) > 0
        initial_messages = provider.calls[0]["messages"]
        user_msg = next(m["content"] for m in initial_messages if m["role"] == "user")
        assert "Verify checkout page fields" in user_msg
        # Assert full history from elsewhere is not leaked into context
        assert "prior_unrelated_history" not in user_msg

    def test_browser_agent_uses_browser_tools_only(self):
        """BrowserAgent tool set contains only browser tools and control tools, no HTTP tool."""
        client = LLMClient(provider=FakeProvider(responses=[]))
        gateway = ToolGateway()

        agent = BrowserAgent(llm_client=client, gateway=gateway)
        tool_names = [t["function"]["name"] for t in agent.tools]

        assert "http_request" not in tool_names
        assert "navigate" in tool_names
        assert "click" in tool_names
        assert "fill" in tool_names
        assert "screenshot" in tool_names
        assert "report_finding" in tool_names
        assert "finish" in tool_names

    def test_browser_agent_returns_findings_with_evidence(self):
        """BrowserAgent returns TaskResult containing Findings with Evidence."""
        task = Task(
            id="task-browser-2",
            goal="Test cart for invalid inputs",
            assignee=AgentType.BROWSER,
            budget={"max_actions": 5, "max_tokens": 5000},
        )

        provider = FakeProvider(responses=[
            make_tool_response("navigate", {"url": "http://localhost:3000/cart.html"}),
            make_tool_response(
                "report_finding",
                {
                    "summary": "Cart allows negative quantity",
                    "evidence_type": "dom_snapshot",
                    "evidence_content": "<input id='qty' value='-1'>",
                },
            ),
            make_tool_response("finish", {"summary": "Completed cart test"}),
        ])
        client = LLMClient(provider=provider)
        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(
            name="navigate",
            handler=lambda url: {"url": url, "snapshot": "<input id='qty'>"},
            is_url_action=True,
        ))

        agent = BrowserAgent(llm_client=client, gateway=gateway)
        result = agent.execute(task, target_url="http://localhost:3000/cart.html")

        assert len(result.findings) == 1
        finding = result.findings[0]
        assert "negative quantity" in finding.summary
        assert len(finding.evidence) >= 1
        assert finding.evidence[0].type == EvidenceType.DOM_SNAPSHOT

    def test_browser_agent_respects_task_budget(self):
        """BrowserAgent stops execution cleanly when its Task budget is reached."""
        task = Task(
            id="task-browser-budget",
            goal="Explore repeatedly until budget limit",
            assignee=AgentType.BROWSER,
            budget={"max_actions": 2, "max_tokens": 5000},
        )

        loop_responses = [
            make_tool_response("navigate", {"url": "http://localhost:3000/page1"}),
            make_tool_response("navigate", {"url": "http://localhost:3000/page2"}),
            make_tool_response("navigate", {"url": "http://localhost:3000/page3"}),
        ]
        provider = FakeProvider(responses=loop_responses)
        client = LLMClient(provider=provider)
        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(
            name="navigate",
            handler=lambda url: {"url": url, "snapshot": "<html></html>"},
            is_url_action=True,
        ))

        agent = BrowserAgent(llm_client=client, gateway=gateway)
        result = agent.execute(task, target_url="http://localhost:3000")

        assert result.budget_exceeded is True
        assert result.actions_count == 2

    def test_browser_agent_returns_steps_not_transcript(self):
        """BrowserAgent returns recorded steps, not raw LLM transcript (per D6)."""
        task = Task(
            id="task-browser-steps",
            goal="Test navigation sequence",
            assignee=AgentType.BROWSER,
            budget={"max_actions": 5, "max_tokens": 5000},
        )

        provider = FakeProvider(responses=[
            make_tool_response("navigate", {"url": "http://localhost:3000/index.html"}),
            make_tool_response("finish", {"summary": "Done navigating"}),
        ])
        client = LLMClient(provider=provider)
        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(
            name="navigate",
            handler=lambda url: {"url": url, "snapshot": "<html></html>"},
            is_url_action=True,
        ))

        agent = BrowserAgent(llm_client=client, gateway=gateway)
        result = agent.execute(task, target_url="http://localhost:3000/index.html")

        # Steps is a list of action fingerprints / step dicts
        assert isinstance(result.steps, list)
        assert len(result.steps) >= 1
        # It must NOT be the raw LLM transcript (no messages dict with system/assistant/user turn dump)
        assert not hasattr(result, "transcript")
        for step in result.steps:
            assert "role" not in step  # Not a message turn!
