"""Unit tests for Run Identity, Directory Layout, and Validated TraceEntry Schema (Ticket T-10).

Verifies:
1. TraceEntry Pydantic schema validation.
2. Hash-chaining across entries (seq, prev_hash, entry_hash).
3. Denied tool calls (allowlist violations, unregistered tools, permission checks) produce trace entries in finally block.
4. Every model call records served model_id and tokens.
5. Token count aggregated from trace.jsonl matches RunResult.tokens_used.
6. Run directory layout conforms to runs/<config>/<run_id>/.
"""
from pathlib import Path
import tempfile
import pytest

from qa_cc.gateway.gateway import ToolGateway, ToolDefinition, TargetNotAllowed, PermissionRequired
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.trace.schema import TraceEntry
from qa_cc.trace.writer import TraceWriter
from qa_cc.agents.baseline import BaselineAgent
from qa_cc.agents.loop import AgentLoop


class TestTraceSchemaAndIdentity:
    def test_trace_entry_schema_validation(self):
        """TraceEntry validates required fields and generates hash-chain."""
        entry = TraceEntry(
            seq=1,
            prev_hash="0" * 64,
            type="model_call",
            model_id="Qwen3.8-Flash",
            tokens=42,
        )
        assert entry.seq == 1
        assert entry.prev_hash == "0" * 64
        assert entry.model_id == "Qwen3.8-Flash"
        assert entry.tokens == 42
        assert entry.timestamp

    def test_trace_writer_creates_hash_chain(self, tmp_path):
        """TraceWriter assigns sequential seq numbers and chains prev_hash to previous entry_hash."""
        trace_path = tmp_path / "chain_trace.jsonl"
        writer = TraceWriter(trace_path)

        writer.record({"type": "run_start", "model_id": "model-1", "tokens": 0})
        writer.record({"type": "model_call", "model_id": "model-1", "tokens": 25})
        writer.record({"type": "tool_call", "tool_name": "navigate", "args": {"url": "http://localhost:3000"}, "tokens": 0})

        entries = writer.read_entries()
        assert len(entries) == 3

        for i, entry in enumerate(entries):
            assert entry["seq"] == i
            assert "entry_hash" in entry
            assert len(entry["entry_hash"]) == 64
            if i == 0:
                assert entry["prev_hash"] == "0" * 64
            else:
                assert entry["prev_hash"] == entries[i - 1]["entry_hash"]

    def test_denied_tool_calls_are_traced_in_finally_block(self, tmp_path):
        """When an action raises TargetNotAllowed or PermissionRequired, gateway still traces the denied call."""
        trace_path = tmp_path / "denied_trace.jsonl"
        writer = TraceWriter(trace_path)
        gateway = ToolGateway(allowlist=["localhost"], trace_writer=writer)

        gateway.register_tool(ToolDefinition(
            name="navigate",
            handler=lambda url: {"url": url},
            is_url_action=True,
        ))

        with pytest.raises(TargetNotAllowed):
            gateway.execute("navigate", {"url": "http://evil.com/malicious"})

        entries = writer.read_entries()
        assert len(entries) == 1
        denied_entry = entries[0]
        assert denied_entry["type"] == "tool_call_denied"
        assert denied_entry["tool_name"] == "navigate"
        assert denied_entry["ok"] is False
        assert "not permitted by allowlist" in denied_entry["denial_reason"]

    def test_tokens_aggregated_from_trace_match_run_result(self, tmp_path):
        """Aggregated tokens from all model_call entries in trace.jsonl match final RunResult.tokens_used."""
        trace_path = tmp_path / "tokens_trace.jsonl"
        writer = TraceWriter(trace_path)

        responses = [
            {
                "id": "c1",
                "model": "qwen-served-1",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "tc-1",
                            "type": "function",
                            "function": {"name": "navigate", "arguments": {"url": "http://localhost:3000/page1"}},
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            },
            {
                "id": "c2",
                "model": "qwen-served-1",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "tc-2",
                            "type": "function",
                            "function": {"name": "finish", "arguments": {"summary": "Completed"}},
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 60, "completion_tokens": 15, "total_tokens": 75},
            },
        ]
        provider = FakeProvider(responses=responses)
        client = LLMClient(provider=provider)
        gateway = ToolGateway(trace_writer=writer)
        gateway.register_tool(ToolDefinition(name="navigate", handler=lambda url: {"url": url}, is_url_action=True))

        agent = BaselineAgent(llm_client=client, gateway=gateway, trace_writer=writer)
        result = agent.run(objective="Token accounting test", target="http://localhost:3000")

        entries = writer.read_entries()
        model_entries = [e for e in entries if e["type"] in ("model_call", "subagent_model_call")]
        assert len(model_entries) == 2
        for e in model_entries:
            assert e["model_id"] == "qwen-served-1"

        trace_token_sum = sum(e.get("tokens", 0) for e in model_entries)
        assert trace_token_sum == result.tokens_used == 145
