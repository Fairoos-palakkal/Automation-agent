"""Tests for ToolGateway — Phase 1.1 (Red -> Green)."""
import os
import tempfile
from pathlib import Path
import pytest

from qa_cc.gateway.gateway import (
    ToolGateway,
    ToolNotFound,
    TargetNotAllowed,
    PermissionRequired,
    ToolDefinition,
)
from qa_cc.trace.writer import TraceWriter


class TestToolGateway:
    def test_gateway_rejects_unknown_tool(self):
        """Calling an unregistered tool raises ToolNotFound."""
        gateway = ToolGateway()
        with pytest.raises(ToolNotFound):
            gateway.execute("non_existent_tool", {})

    def test_gateway_enforces_allowlist(self):
        """A navigate tool call to a non-allowlisted target raises TargetNotAllowed."""
        gateway = ToolGateway(allowlist=["localhost", "127.0.0.1", "benchmark/own_site"])
        gateway.register_tool(
            ToolDefinition(
                name="navigate",
                handler=lambda url: f"navigated to {url}",
                is_url_action=True,
            )
        )

        # Allowed target
        result = gateway.execute("navigate", {"url": "http://localhost:3000"})
        assert result == "navigated to http://localhost:3000"

        # Disallowed target
        with pytest.raises(TargetNotAllowed):
            gateway.execute("navigate", {"url": "https://malicious-external-site.com/exploit"})

    def test_gateway_scrubs_secrets_from_args(self, monkeypatch):
        """Tool args containing sensitive/secret values are scrubbed in trace logs."""
        monkeypatch.setenv("SECRET_TOKEN", "super-secret-token-xyz")

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.jsonl"
            trace_writer = TraceWriter(trace_path)

            gateway = ToolGateway(trace_writer=trace_writer, secret_keys=["SECRET_TOKEN"])
            gateway.register_tool(
                ToolDefinition(
                    name="echo",
                    handler=lambda text: f"echo: {text}",
                )
            )

            result = gateway.execute("echo", {"text": "My key is super-secret-token-xyz"})
            assert result == "echo: My key is super-secret-token-xyz"

            # Check trace output
            entries = trace_writer.read_entries()
            assert len(entries) == 1
            entry = entries[0]
            assert "super-secret-token-xyz" not in str(entry["args"])
            assert "[SCRUBBED]" in str(entry["args"])

    def test_gateway_records_tool_call_in_trace(self):
        """After execution, a trace entry exists for the tool call with name, args, result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.jsonl"
            trace_writer = TraceWriter(trace_path)

            gateway = ToolGateway(trace_writer=trace_writer)
            gateway.register_tool(
                ToolDefinition(
                    name="click",
                    handler=lambda selector: f"clicked {selector}",
                )
            )

            result = gateway.execute("click", {"selector": "#submit-btn"})
            assert result == "clicked #submit-btn"

            entries = trace_writer.read_entries()
            assert len(entries) == 1
            assert entries[0]["type"] == "tool_call"
            assert entries[0]["tool_name"] == "click"
            assert entries[0]["args"] == {"selector": "#submit-btn"}
            assert entries[0]["result"] == "clicked #submit-btn"

    def test_gateway_enforces_permissions(self):
        """A tool requiring explicit permissions raises PermissionRequired when not granted."""
        gateway = ToolGateway(granted_permissions=set())
        gateway.register_tool(
            ToolDefinition(
                name="destructive_reset",
                handler=lambda: "reset complete",
                required_permission="admin_destructive",
            )
        )

        with pytest.raises(PermissionRequired):
            gateway.execute("destructive_reset", {})

        # Grant permission and verify it passes
        gateway.grant_permission("admin_destructive")
        assert gateway.execute("destructive_reset", {}) == "reset complete"
