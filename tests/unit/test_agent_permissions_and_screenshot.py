"""Test T-20: Per-agent caller permissions and screenshot path ownership (F-06).

Verifies that:
1. Browser caller invoking http_request raises PermissionRequired.
2. API caller invoking browser tools raises PermissionRequired.
3. Baseline caller can invoke both.
4. Screenshots ignore model-supplied paths (e.g., /etc/cron.d/x.png) and
   generate unique paths per step.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from qa_cc.gateway.gateway import ToolGateway, ToolDefinition, PermissionRequired
from qa_cc.trace.writer import TraceWriter
from qa_cc.agents.browser import BrowserAgent, BROWSER_TOOLS
from qa_cc.agents.api import APIAgent
from qa_cc.agents.plan import Task
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider


def test_per_agent_caller_permissions(tmp_path: Path):
    trace_file = tmp_path / "trace.jsonl"
    writer = TraceWriter(trace_file, run_id="run-perm-test")
    gw = ToolGateway(trace_writer=writer)

    gw.register_tool(ToolDefinition(
        name="navigate",
        handler=lambda url: {"url": url},
        is_url_action=True,
        allowed_callers={"baseline", "browser"},
    ))
    gw.register_tool(ToolDefinition(
        name="http_request",
        handler=lambda url, method="GET": {"status": 200},
        is_url_action=True,
        allowed_callers={"baseline", "api"},
    ))

    # Browser caller calling navigate: OK
    res = gw.execute("navigate", {"url": "http://localhost:3000"}, caller="browser")
    assert res["url"] == "http://localhost:3000"

    # Browser caller calling http_request: PermissionRequired
    with pytest.raises(PermissionRequired) as exc_info:
        gw.execute("http_request", {"url": "http://localhost:3000"}, caller="browser")
    assert "browser" in str(exc_info.value)
    assert "http_request" in str(exc_info.value)

    # API caller calling navigate: PermissionRequired
    with pytest.raises(PermissionRequired) as exc_info:
        gw.execute("navigate", {"url": "http://localhost:3000"}, caller="api")
    assert "api" in str(exc_info.value)

    # Baseline caller calling both: OK
    res_nav = gw.execute("navigate", {"url": "http://localhost:3000"}, caller="baseline")
    assert res_nav["url"] == "http://localhost:3000"
    res_http = gw.execute("http_request", {"url": "http://localhost:3000"}, caller="baseline")
    assert res_http["status"] == 200

    # Verify denial traced
    entries = [json.loads(line) for line in trace_file.read_text().splitlines() if line.strip()]
    denials = [e for e in entries if e["type"] == "tool_call_denied"]
    assert len(denials) == 2
    assert denials[0]["tool_name"] == "http_request"
    assert denials[0]["caller"] == "browser"


def test_screenshot_path_ownership_and_uniqueness(tmp_path: Path):
    """The gateway owns the screenshot path; model-supplied path is ignored; unique per step."""
    trace_file = tmp_path / "trace.jsonl"
    writer = TraceWriter(trace_file, run_id="run-screenshot-test")
    artifacts_dir = tmp_path / "artifacts"
    gw = ToolGateway(trace_writer=writer, artifacts_dir=artifacts_dir)

    def mock_screenshot_saver(dest_path: str):
        p = Path(dest_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"PNGDATA")
        return str(dest_path)

    gw.register_screenshot_tool(mock_screenshot_saver)

    # Model supplies malicious path; gateway ignores it and writes into artifacts_dir
    res1 = gw.execute("screenshot", {"path": "/etc/cron.d/x.png"}, caller="browser")
    assert "/etc/cron.d/x.png" not in res1["path"]
    assert str(artifacts_dir) in res1["path"]
    assert Path(res1["path"]).exists()

    # Second screenshot produces a unique path
    res2 = gw.execute("screenshot", {}, caller="browser")
    assert res1["path"] != res2["path"]
    assert Path(res2["path"]).exists()


def test_browser_agent_cannot_call_http_request():
    """BrowserAgent executing http_request receives PermissionRequired."""
    gw = ToolGateway()
    gw.register_tool(ToolDefinition(
        name="http_request",
        handler=lambda url, method="GET": {"status": 200},
        allowed_callers={"baseline", "api"},
    ))

    provider = FakeProvider(responses=[{
        "id": "c1",
        "model": "fake",
        "choices": [{
            "message": {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "http_request", "arguments": json.dumps({"url": "http://localhost:3000"})},
                }],
            }
        }],
    }])
    client = LLMClient(provider=provider)
    agent = BrowserAgent(llm_client=client, gateway=gw)

    task = Task(id="t1", goal="Test", assignee="browser", budget={"max_actions": 5, "max_tokens": 1000})
    result = agent.execute(task, target_url="http://localhost:3000", max_turns=1)
    # The step log should record that the action failed with PermissionRequired
    failed_steps = [s for s in result.step_log.steps if not s.ok]
    assert len(failed_steps) == 1
    assert "not authorized to use tool 'http_request'" in (failed_steps[0].error or "")
