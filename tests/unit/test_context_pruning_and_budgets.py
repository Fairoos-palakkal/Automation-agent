"""Tests for Context Pruning, Interactive Element Index, and Bounded Budgets (T-19, F-13).

Verifies:
1. 25-turn FakeProvider run shows roughly linear prompt growth (not quadratic).
2. Interactive element index extracts buttons, links, inputs, and forms within 2-4K chars.
3. Token cap stops execution within 1 call of exceeding max_tokens.
4. Model-call budget (max_model_calls) stops execution when reached.
5. Wall-clock budget (max_duration_seconds) stops execution when exceeded.
6. max_turns is derived dynamically from remaining budget.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
import pytest

from qa_cc.trace.run_state import RunState, BudgetExceeded
from qa_cc.agents.loop import AgentLoop
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.tools.browser import extract_interactive_elements


def test_interactive_element_index():
    """Extracts interactive controls (buttons, links, inputs) into a compact index."""
    html = """
    <html>
    <head><title>Test Store</title></head>
    <body>
        <nav>
            <a href="/home">Home</a>
            <a href="/catalog">Catalog</a>
        </nav>
        <main>
            <h1>Products</h1>
            <input type="text" id="search-box" name="q" placeholder="Search products..." />
            <button id="search-btn" type="submit">Search</button>
            <div class="product">
                <button class="add-to-cart" data-id="101">Add Widget 1</button>
            </div>
        </main>
        <footer>
            <form action="/subscribe" method="POST">
                <input type="email" name="email" placeholder="Newsletter" />
                <button type="submit" id="sub-btn">Subscribe</button>
            </form>
            <a href="/contact">Contact Us</a>
        </footer>
    </body>
    </html>
    """
    index = extract_interactive_elements(html, max_chars=4000)

    assert "Search products..." in index or "#search-box" in index
    assert "Search" in index
    assert "Add Widget 1" in index
    # Footer elements at the end are NOT cut off
    assert "Subscribe" in index or "Newsletter" in index
    assert "Contact Us" in index
    assert len(index) <= 4000


def test_25_turn_prompt_growth_is_roughly_linear():
    """25-turn run prunes older observations to one-line summaries so prompt growth is linear."""
    recorded_prompt_lengths = []

    class MeasuringProvider(FakeProvider):
        def chat(self, messages, tools=None):
            # Measure characters in the prompt messages passed to the LLM
            prompt_str = json.dumps(messages)
            recorded_prompt_lengths.append(len(prompt_str))
            turn = len(recorded_prompt_lengths)
            if turn < 25:
                return {
                    "id": f"turn-{turn}",
                    "model": "measuring-fake",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": f"tc-{turn}",
                                "type": "function",
                                "function": {
                                    "name": "click",
                                    "arguments": json.dumps({"selector": f"#btn-{turn}"}),
                                },
                            }],
                        }
                    }],
                    "usage": {"prompt_tokens": len(prompt_str) // 4, "completion_tokens": 10, "total_tokens": (len(prompt_str) // 4) + 10},
                }
            else:
                return {
                    "id": f"turn-{turn}",
                    "model": "measuring-fake",
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "tool_calls": [{
                                "id": f"tc-{turn}",
                                "type": "function",
                                "function": {
                                    "name": "finish",
                                    "arguments": json.dumps({"summary": "25 turns complete"}),
                                },
                            }],
                        }
                    }],
                    "usage": {"prompt_tokens": len(prompt_str) // 4, "completion_tokens": 5, "total_tokens": (len(prompt_str) // 4) + 5},
                }

    provider = MeasuringProvider(responses=[])
    client = LLMClient(provider=provider)
    gw = ToolGateway()
    # Large 5KB observation returned by each click
    gw.register_tool(ToolDefinition(
        name="click",
        handler=lambda selector: {"status": "ok", "snapshot": f"<div>Large DOM Content {selector} " + ("x" * 4000) + "</div>"},
    ))
    gw.register_tool(ToolDefinition(
        name="finish",
        handler=lambda summary: {"status": "ok"},
    ))

    loop = AgentLoop(
        client=client,
        gateway=gw,
        tools=[
            {"type": "function", "function": {"name": "click", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "finish", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}}}},
        ],
        system_prompt="Test agent prompt",
        run_state=RunState(max_actions=50, max_tokens=1_000_000),
    )

    loop.run(objective="Explore", target="http://localhost:3000", max_turns=25)

    assert len(recorded_prompt_lengths) == 25
    # In quadratic growth without pruning, 25 turns * 4KB would exceed 100KB per prompt!
    # With pruning of older observations to 1-line summaries:
    # prompt length at turn 25 should remain bounded and reasonably close to turn 5
    # (specifically, turn 25 should be less than 3x turn 5 prompt length)
    len_turn_5 = recorded_prompt_lengths[4]
    len_turn_25 = recorded_prompt_lengths[24]
    ratio = len_turn_25 / len_turn_5
    assert ratio < 3.0, f"Prompt grew quadratically: turn 5 was {len_turn_5} chars, turn 25 was {len_turn_25} chars (ratio {ratio:.2f})"


def test_token_budget_cap_stops_run_within_one_call():
    """RunState token cap stops execution within 1 call of exceeding max_tokens."""
    rs = RunState(max_actions=50, max_tokens=500)
    rs.record_tokens(300)
    rs.check_budget()  # 300 <= 500, ok

    rs.record_tokens(300)  # total 600 > 500
    with pytest.raises(BudgetExceeded) as exc_info:
        rs.check_budget()
    assert "token budget exceeded" in str(exc_info.value)


def test_max_model_calls_budget():
    """RunState enforces max_model_calls budget."""
    rs = RunState(max_actions=50, max_tokens=100_000, max_model_calls=3)
    rs.record_model_call()
    rs.check_budget()
    rs.record_model_call()
    rs.check_budget()
    rs.record_model_call()
    with pytest.raises(BudgetExceeded) as exc_info:
        rs.check_budget()
    assert "model-call budget exceeded" in str(exc_info.value)


def test_wall_clock_duration_budget():
    """RunState enforces max_duration_seconds budget."""
    rs = RunState(max_actions=50, max_tokens=100_000, max_duration_seconds=0.05)
    rs.start_timer()
    time.sleep(0.08)
    with pytest.raises(BudgetExceeded) as exc_info:
        rs.check_budget()
    assert "wall-clock duration budget exceeded" in str(exc_info.value)


def test_derived_max_turns():
    """AgentLoop derives max_turns from remaining budget."""
    rs = RunState(max_actions=5, max_tokens=100_000)
    rs.record_action("a1")
    rs.record_action("a2")
    # 2 actions used out of 5 -> remaining actions = 3
    turns = rs.remaining_turns(default_max=25)
    assert turns == 3
