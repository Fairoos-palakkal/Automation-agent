"""Tests for Loop Detector Sliding Window and Recovery — Ticket T-22 (F-17)."""
import json
import pytest

from qa_cc.agents.loop import AgentLoop
from qa_cc.agents.loop_detector import LoopDetector, RecoveryAction
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.trace.run_state import RunState
from qa_cc.trace.writer import TraceWriter


class TestLoopDetectorSlidingWindow:
    def test_abab_pattern_detection(self):
        """Loop detector catches alternating ABAB patterns and progresses through recovery."""
        detector = LoopDetector()

        # Step 1: A
        assert detector.check("action_A", "obs_A") == RecoveryAction.CONTINUE
        # Step 2: B
        assert detector.check("action_B", "obs_B") == RecoveryAction.CONTINUE
        # Step 3: A
        assert detector.check("action_A", "obs_A") == RecoveryAction.CONTINUE
        # Step 4: B -> ABAB matches, triggers RE_OBSERVE
        assert detector.check("action_B", "obs_B") == RecoveryAction.RE_OBSERVE

        # Step 5: A
        assert detector.check("action_A", "obs_A") == RecoveryAction.CONTINUE
        # Step 6: B -> ABABAB matches, triggers TRY_ALTERNATE
        assert detector.check("action_B", "obs_B") == RecoveryAction.TRY_ALTERNATE

        # Step 7: A
        assert detector.check("action_A", "obs_A") == RecoveryAction.CONTINUE
        # Step 8: B -> ABABABAB matches, triggers TERMINATE_INCONCLUSIVE
        assert detector.check("action_B", "obs_B") == RecoveryAction.TERMINATE_INCONCLUSIVE

    def test_abcabc_pattern_detection(self):
        """Loop detector catches ABCABC patterns (period 3) and progresses through recovery."""
        detector = LoopDetector()

        # First cycle: A, B, C
        assert detector.check("act_1", "obs_1") == RecoveryAction.CONTINUE
        assert detector.check("act_2", "obs_2") == RecoveryAction.CONTINUE
        assert detector.check("act_3", "obs_3") == RecoveryAction.CONTINUE

        # Second cycle: A, B, C -> ABCABC triggers RE_OBSERVE
        assert detector.check("act_1", "obs_1") == RecoveryAction.CONTINUE
        assert detector.check("act_2", "obs_2") == RecoveryAction.CONTINUE
        assert detector.check("act_3", "obs_3") == RecoveryAction.RE_OBSERVE

        # Third cycle: A, B, C -> triggers TRY_ALTERNATE
        assert detector.check("act_1", "obs_1") == RecoveryAction.CONTINUE
        assert detector.check("act_2", "obs_2") == RecoveryAction.CONTINUE
        assert detector.check("act_3", "obs_3") == RecoveryAction.TRY_ALTERNATE

        # Fourth cycle: A, B, C -> triggers TERMINATE_INCONCLUSIVE
        assert detector.check("act_1", "obs_1") == RecoveryAction.CONTINUE
        assert detector.check("act_2", "obs_2") == RecoveryAction.CONTINUE
        assert detector.check("act_3", "obs_3") == RecoveryAction.TERMINATE_INCONCLUSIVE

    def test_breaking_pattern_resets_loop(self):
        """An action breaking the pattern stops the cycle progression."""
        detector = LoopDetector()

        detector.check("act_A", "obs_A")
        detector.check("act_B", "obs_B")
        detector.check("act_A", "obs_A")
        assert detector.check("act_B", "obs_B") == RecoveryAction.RE_OBSERVE

        # Model breaks the loop by doing action C
        assert detector.check("act_C", "obs_C") == RecoveryAction.CONTINUE
        # Then doing A, B is not yet a 2-cycle
        assert detector.check("act_A", "obs_A") == RecoveryAction.CONTINUE
        assert detector.check("act_B", "obs_B") == RecoveryAction.CONTINUE


class TestAgentLoopRecoveryIntegration:
    def test_agent_loop_terminates_on_repeated_cycle(self, tmp_path):
        """AgentLoop injects recovery messages on loop and terminates with 'loop_terminated'."""
        trace_path = tmp_path / "trace.jsonl"
        trace_writer = TraceWriter(trace_path)

        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(
            name="click",
            handler=lambda selector: {"url": "http://localhost:3000/page", "snapshot": "Page DOM"},
            allowed_callers={"browser"},
        ))

        def make_tool_call(tool_name: str, args: dict):
            return {
                "id": "call-1",
                "model": "fake-model",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "tc-1",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": json.dumps(args)},
                        }],
                    }
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            }

        # Model repeatedly emits click #btnA, click #btnB (ABAB pattern)
        responses = [
            make_tool_call("click", {"selector": "#btnA"}),
            make_tool_call("click", {"selector": "#btnB"}),
            make_tool_call("click", {"selector": "#btnA"}),
            make_tool_call("click", {"selector": "#btnB"}),  # Trigger 1: RE_OBSERVE
            make_tool_call("click", {"selector": "#btnA"}),
            make_tool_call("click", {"selector": "#btnB"}),  # Trigger 2: TRY_ALTERNATE
            make_tool_call("click", {"selector": "#btnA"}),
            make_tool_call("click", {"selector": "#btnB"}),  # Trigger 3: TERMINATE_INCONCLUSIVE
        ]

        provider = FakeProvider(responses=responses)
        client = LLMClient(provider=provider)
        run_state = RunState(max_actions=20, max_tokens=10000)

        agent_loop = AgentLoop(
            agent_name="browser",
            client=client,
            gateway=gateway,
            tools=[],
            run_state=run_state,
            system_prompt="You are a test browser agent.",
            trace_writer=trace_writer,
        )

        result = agent_loop.run(target="http://localhost:3000/page", max_turns=10)

        # Result status must be loop_terminated
        assert result.status == "loop_terminated"
        assert result.loop_recovery_triggered is True

        # Trace entries must include loop_recovery events
        entries = trace_writer.read_entries()
        recovery_events = [e for e in entries if e.get("type") == "loop_recovery"]
        assert len(recovery_events) >= 3
        actions = [e["recovery_action"] for e in recovery_events]
        assert "RE_OBSERVE" in actions
        assert "TRY_ALTERNATE" in actions
        assert "TERMINATE_INCONCLUSIVE" in actions
