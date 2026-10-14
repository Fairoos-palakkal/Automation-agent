"""Tests for LoopDetector and Recovery State Machine — Phase 1.5 (Red -> Green)."""
import pytest

from qa_cc.agents.loop_detector import (
    LoopDetector,
    RecoveryAction,
    compute_action_fingerprint,
    compute_observation_fingerprint,
)


class TestLoopDetector:
    def test_fingerprint_computation(self):
        """Action and observation fingerprints produce deterministic hashes."""
        fp1 = compute_action_fingerprint("click", {"selector": "#btn"}, "http://localhost:3000")
        fp2 = compute_action_fingerprint("click", {"selector": "#btn"}, "http://localhost:3000")
        fp3 = compute_action_fingerprint("click", {"selector": "#other"}, "http://localhost:3000")

        assert fp1 == fp2
        assert fp1 != fp3
        assert isinstance(fp1, str) and len(fp1) > 0

        obs_fp1 = compute_observation_fingerprint("<html><body><h1>Same</h1></body></html>")
        obs_fp2 = compute_observation_fingerprint("<html><body><h1>Same</h1></body></html>")
        obs_fp3 = compute_observation_fingerprint("<html><body><h1>Different</h1></body></html>")

        assert obs_fp1 == obs_fp2
        assert obs_fp1 != obs_fp3

    def test_no_loop_on_unique_actions(self):
        """Unique (action, observation) pairs do not trigger a loop."""
        detector = LoopDetector(threshold=3)

        assert detector.check("act_1", "obs_1") == RecoveryAction.CONTINUE
        assert detector.check("act_2", "obs_2") == RecoveryAction.CONTINUE
        assert detector.check("act_3", "obs_3") == RecoveryAction.CONTINUE

    def test_loop_detected_after_three_repeats(self):
        """Repeating the exact same (action, observation) 3 consecutive times triggers recovery."""
        detector = LoopDetector(threshold=3)

        assert detector.check("act_dup", "obs_dup") == RecoveryAction.CONTINUE
        assert detector.check("act_dup", "obs_dup") == RecoveryAction.CONTINUE
        # 3rd time hits threshold
        action = detector.check("act_dup", "obs_dup")
        assert action in (RecoveryAction.RE_OBSERVE, RecoveryAction.TRIGGER_RECOVERY)

    def test_recovery_sequence(self):
        """Recovery state machine progresses: RE_OBSERVE -> TRY_ALTERNATE -> TERMINATE_INCONCLUSIVE."""
        detector = LoopDetector(threshold=3)

        # 3 repetitions
        detector.check("loop_act", "loop_obs")
        detector.check("loop_act", "loop_obs")
        act1 = detector.check("loop_act", "loop_obs")
        assert act1 == RecoveryAction.RE_OBSERVE

        # Continued loop after re-observe
        act2 = detector.check("loop_act", "loop_obs")
        assert act2 == RecoveryAction.TRY_ALTERNATE

        # Still stuck -> terminate
        act3 = detector.check("loop_act", "loop_obs")
        assert act3 == RecoveryAction.TERMINATE_INCONCLUSIVE
