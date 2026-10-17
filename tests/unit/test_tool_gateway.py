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

    @pytest.mark.parametrize("bypass_url", [
        "http://localhost.evil.com",
        "https://evil.com/?next=localhost",
        "http://localhost@evil.com/",
        "http://evil.com/localhost",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "http://127.0.0.1.attacker.com",
        "http://attacker.com#localhost",
        "http://localhost:3001",
    ])
    def test_gateway_blocks_allowlist_bypasses(self, bypass_url):
        """Gateway raises TargetNotAllowed on substring/lookalike/redirect/userinfo bypass attempts."""
        gateway = ToolGateway(allowlist=["localhost:3000", "127.0.0.1:3000"])
        gateway.register_tool(
            ToolDefinition(
                name="navigate",
                handler=lambda url: f"navigated to {url}",
                is_url_action=True,
            )
        )
        with pytest.raises(TargetNotAllowed):
            gateway.execute("navigate", {"url": bypass_url})

    @pytest.mark.parametrize("bypass_url", [
        "http://localhost.evil.com",
        "https://evil.com/?next=localhost",
        "http://localhost@evil.com/",
        "http://evil.com/localhost",
        "http://127.0.0.1.evil.com",
    ])
    def test_gateway_blocks_standard_allowlist_substring_bypasses(self, bypass_url):
        """Gateway raises TargetNotAllowed on substring bypasses when allowlist is standard ['localhost', '127.0.0.1']."""
        gateway = ToolGateway(allowlist=["localhost", "127.0.0.1"])
        gateway.register_tool(
            ToolDefinition(
                name="navigate",
                handler=lambda url: f"navigated to {url}",
                is_url_action=True,
            )
        )
        with pytest.raises(TargetNotAllowed):
            gateway.execute("navigate", {"url": bypass_url})


    @pytest.mark.parametrize("valid_url", [
        "http://localhost:3000",
        "http://localhost:3000/cart.html",
        "http://LOCALHOST:3000/index.html",
        "http://localhost.:3000/catalog",
        "http://127.0.0.1:3000/api",
    ])
    def test_gateway_allows_valid_exact_host_urls(self, valid_url):
        """Gateway allows exact host:port matches including uppercase and trailing dot."""
        gateway = ToolGateway(allowlist=["localhost:3000", "127.0.0.1:3000"])
        gateway.register_tool(
            ToolDefinition(
                name="navigate",
                handler=lambda url: f"navigated to {url}",
                is_url_action=True,
            )
        )
        result = gateway.execute("navigate", {"url": valid_url})
        assert "navigated to" in result

