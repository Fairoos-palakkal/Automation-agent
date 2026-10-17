"""Unit tests for shared AgentLoop and StepLog (Ticket T-08).

Verifies:
1. AgentLoop executes tools and handles finish/report_finding.
2. StepLog records actions with sequential step IDs and tool details.
3. LLM failure produces status='llm_error' and creates an 'llm_error' trace event.
4. Malformed tool-arg JSON is rejected with an error instead of passing empty dicts.
5. BaselineAgent delegates cleanly to AgentLoop while preserving existing semantics.
"""
from pathlib import Path
import tempfile
import pytest

from qa_cc.agents.loop import AgentLoop, AgentLoopResult
from qa_cc.agents.step_log import StepLog, StepEntry
from qa_cc.agents.baseline import BaselineAgent, RunResult
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.trace.run_state import RunState
from qa_cc.trace.writer import TraceWriter
from qa_cc.verdict.evidence import EvidenceType


def make_tool_response(tool_name: str, args: dict | str, content: str = ""):
    return {
        "id": "call-1",
        "model": "fake-model-qwen",
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


class TestAgentLoopAndStepLog:
    def test_step_log_records_sequential_steps(self):
        step_log = StepLog()
        s1 = step_log.record_step(
            tool="navigate",
            args={"url": "http://localhost:3000"},
            url_before="http://localhost:3000",
            ok=True,
            result={"url": "http://localhost:3000", "snapshot": "<html>Home</html>"},
        )
        s2 = step_log.record_step(
            tool="click",
            args={"selector": "#buy-btn"},
            url_before="http://localhost:3000",
            ok=False,
            error="Element not found",
        )

        assert s1.step_id == "step-1"
        assert s1.tool == "navigate"
        assert s1.ok is True
        assert s2.step_id == "step-2"
        assert s2.tool == "click"
        assert s2.ok is False
        assert s2.error == "Element not found"
        assert len(step_log.steps) == 2

    def test_agent_loop_basic_execution_and_step_recording(self):
        provider = FakeProvider(
            responses=[
                make_tool_response("navigate", {"url": "http://localhost:3000/catalog.html"}),
                make_tool_response("finish", {"summary": "Exploration finished successfully"}),
            ]
        )
        client = LLMClient(provider=provider)
        gateway = ToolGateway()
        called_nav = []
        gateway.register_tool(
            ToolDefinition(
                name="navigate",
                handler=lambda url: (called_nav.append(url), {"url": url, "snapshot": "<html>Catalog</html>"})[1],
                is_url_action=True,
            )
        )

        step_log = StepLog()
        run_state = RunState(max_actions=5)
        loop = AgentLoop(
            client=client,
            gateway=gateway,
            tools=[{"type": "function", "function": {"name": "navigate"}}, {"type": "function", "function": {"name": "finish"}}],
            system_prompt="You are a QA agent.",
            run_state=run_state,
            step_log=step_log,
            agent_name="baseline",
        )

        result = loop.run(objective="Explore catalog", target="http://localhost:3000/catalog.html")

        assert result.status == "completed"
        assert len(called_nav) == 1
        assert called_nav[0] == "http://localhost:3000/catalog.html"
        assert len(step_log.steps) >= 1
        assert step_log.steps[0].tool == "navigate"
        assert result.summary == "Exploration finished successfully"

    def test_agent_loop_handles_llm_failure(self):
        """When client.chat raises an error, status becomes 'llm_error' and error is traced."""
        class FailingProvider:
            model = "error-model"
            def chat(self, messages, tools=None):
                raise RuntimeError("LLM API connection timed out")

        client = LLMClient(provider=FailingProvider())
        gateway = ToolGateway()

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.jsonl"
            trace_writer = TraceWriter(trace_path)

            loop = AgentLoop(
                client=client,
                gateway=gateway,
                tools=[],
                system_prompt="Test agent",
                trace_writer=trace_writer,
            )

            result = loop.run(objective="Test LLM failure", target="http://localhost:3000")

            assert result.status == "llm_error"
            assert "LLM API connection timed out" in result.summary or "llm_error" in result.summary

            entries = trace_writer.read_entries()
            llm_errors = [e for e in entries if e.get("type") == "llm_error"]
            assert len(llm_errors) == 1
            assert "LLM API connection timed out" in llm_errors[0].get("error", "")

    def test_agent_loop_rejects_malformed_tool_args(self):
        """Malformed tool arguments JSON is rejected with error, not executed as {}."""
        executed_with = []
        gateway = ToolGateway()
        gateway.register_tool(
            ToolDefinition(
                name="click",
                handler=lambda **kwargs: executed_with.append(kwargs),
            )
        )

        # Response with raw unclosed JSON string
        malformed_call = {
            "id": "call-bad-json",
            "model": "fake-model",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "tc-bad",
                                "type": "function",
                                "function": {
                                    "name": "click",
                                    "arguments": '{"selector": "#broken',  # unclosed JSON
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"total_tokens": 10},
        }

        # Follow up with finish
        finish_call = make_tool_response("finish", {"summary": "Done after bad args"})

        provider = FakeProvider(responses=[malformed_call, finish_call])
        client = LLMClient(provider=provider)

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.jsonl"
            trace_writer = TraceWriter(trace_path)

            loop = AgentLoop(
                client=client,
                gateway=gateway,
                tools=[{"type": "function", "function": {"name": "click"}}, {"type": "function", "function": {"name": "finish"}}],
                system_prompt="Test agent",
                trace_writer=trace_writer,
            )

            result = loop.run(objective="Test bad JSON", target="http://localhost:3000")

            # The tool MUST NOT be executed with empty dictionary
            assert len(executed_with) == 0

            # Trace MUST record invalid_args
            entries = trace_writer.read_entries()
            invalid_arg_entries = [e for e in entries if e.get("type") == "invalid_args"]
            assert len(invalid_arg_entries) == 1
            assert invalid_arg_entries[0]["tool_name"] == "click"

            # The message sent back to the model in turn 2 should contain an error about malformed JSON
            assert len(provider.calls) == 2
            second_call_messages = provider.calls[1]["messages"]
            tool_msg = next((m for m in second_call_messages if m.get("role") == "tool"), None)
            assert tool_msg is not None
            assert "Malformed JSON" in tool_msg["content"] or "Error" in tool_msg["content"]

    def test_baseline_agent_uses_agent_loop_and_surfaces_llm_error(self):
        """BaselineAgent delegates to AgentLoop and exposes status='llm_error' on failure."""
        class FailingProvider:
            model = "error-model"
            def chat(self, messages, tools=None):
                raise ConnectionError("Connection refused")

        client = LLMClient(provider=FailingProvider())
        gateway = ToolGateway()
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.jsonl"
            trace_writer = TraceWriter(trace_path)

            agent = BaselineAgent(
                llm_client=client,
                gateway=gateway,
                trace_writer=trace_writer,
            )
            result = agent.run(objective="Test", target="http://localhost:3000")

            assert isinstance(result, RunResult)
            assert result.status == "llm_error"
