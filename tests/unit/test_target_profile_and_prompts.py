"""Test T-16: Target Profile instead of hard-coded prompts (F-07).

Verifies that:
1. Grep test: zero target-specific strings (Juice Shop selectors, endpoints,
   SQLi payloads, Noshery/cookie strings) exist in agent prompt modules.
2. TargetProfile loads, serializes, and formats cleanly.
3. Profile is recorded in the trace and can be passed to agents.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import pytest

from qa_cc.config.target_profile import TargetProfile
from qa_cc.agents.baseline import BaselineAgent
from qa_cc.agents.browser import BrowserAgent
from qa_cc.agents.api import APIAgent
from qa_cc.agents.planner import Planner
from qa_cc.trace.writer import TraceWriter
from qa_cc.trace.run_state import RunState
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.gateway.gateway import ToolGateway


def test_no_target_specific_strings_in_agent_prompts():
    """Requirement F-07: Grep test finds no target-specific strings in prompt modules.
    Matches: juice, noshery, rest/user, or 1=1, Me want.
    """
    agents_dir = Path("src/qa_cc/agents")
    forbidden_pattern = re.compile(r"juice|noshery|rest/user|or 1=1|Me want", re.IGNORECASE)

    violations = []
    for py_file in agents_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for line_num, line in enumerate(content.splitlines(), start=1):
            if forbidden_pattern.search(line):
                violations.append(f"{py_file.name}:{line_num}: {line.strip()}")

    assert not violations, f"Found target-specific strings in agents:\n" + "\n".join(violations)


def test_target_profile_load_and_format(tmp_path: Path):
    """Test loading and formatting a TargetProfile."""
    profile_data = {
        "name": "Test Target",
        "description": "A demo web app",
        "hints": ["Look out for modal banners", "Check authentication forms"],
        "endpoints": ["/api/v1/auth", "/api/v1/items"],
        "selectors": ["#login-btn", ".item-card"],
        "metadata": {"environment": "staging"},
    }
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_data), encoding="utf-8")

    profile = TargetProfile.load(profile_file)
    assert profile.name == "Test Target"
    assert len(profile.hints) == 2
    assert len(profile.endpoints) == 2

    formatted = profile.format_for_prompt()
    assert "Test Target" in formatted
    assert "/api/v1/auth" in formatted
    assert "Look out for modal banners" in formatted

    d = profile.to_dict()
    assert d["name"] == "Test Target"
    assert d["metadata"]["environment"] == "staging"


def test_target_profile_recorded_in_trace(tmp_path: Path):
    """Target Profile is recorded in the trace on run_start."""
    trace_path = tmp_path / "trace.jsonl"
    trace_writer = TraceWriter(trace_path, run_id="run-t16-test")

    profile = TargetProfile(
        name="Target A",
        hints=["Test hint 1"],
    )

    provider = FakeProvider(responses=[{
        "id": "c1",
        "model": "fake",
        "choices": [{
            "message": {
                "role": "assistant",
                "tool_calls": [{
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "finish", "arguments": {"summary": "Done"}},
                }],
            }
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }])
    client = LLMClient(provider=provider)
    gateway = ToolGateway(allowlist=["localhost"])

    agent = BaselineAgent(
        llm_client=client,
        gateway=gateway,
        trace_writer=trace_writer,
        target_profile=profile,
    )
    result = agent.run(objective="Explore target", target="http://localhost:3000")
    assert result is not None

    # Verify trace entries
    entries = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
    run_start = next(e for e in entries if e["type"] == "run_start")
    assert "target_profile" in run_start
    assert run_start["target_profile"]["name"] == "Target A"
