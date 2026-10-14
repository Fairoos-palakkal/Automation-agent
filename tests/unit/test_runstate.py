"""Tests for RunState + BudgetEnforcer — Phase 0.5 (Red → Green)"""
import pytest
from qa_cc.trace.run_state import RunState, BudgetExceeded


def make_finding(id="f1"):
    return {"id": id, "summary": "A defect", "evidence": []}


class TestRunState:
    def test_runstate_starts_within_budget(self):
        """A fresh RunState with limits reports within_budget = True."""
        state = RunState(max_actions=25, max_tokens=10_000)
        # Should not raise; still within budget
        state.check_budget()  # no exception

    def test_runstate_action_budget_exceeded(self):
        """After recording max_actions + 1 actions, check_budget() raises BudgetExceeded."""
        state = RunState(max_actions=3, max_tokens=10_000)
        for _ in range(3):
            state.record_action(fingerprint="fp")

        with pytest.raises(BudgetExceeded, match="action"):
            state.check_budget()

    def test_runstate_token_budget_exceeded(self):
        """After recording tokens past the cap, check_budget() raises BudgetExceeded."""
        state = RunState(max_actions=100, max_tokens=50)
        state.record_tokens(51)

        with pytest.raises(BudgetExceeded, match="token"):
            state.check_budget()

    def test_runstate_tracks_findings(self):
        """add_finding(f) makes the finding retrievable via .findings."""
        state = RunState(max_actions=25, max_tokens=10_000)
        f = make_finding("f1")

        state.add_finding(f)

        assert f in state.findings

    def test_runstate_tracks_history_fingerprints(self):
        """record_action(fingerprint) stores it; .has_fingerprint(fp) returns True."""
        state = RunState(max_actions=25, max_tokens=10_000)

        state.record_action(fingerprint="abc123")

        assert state.has_fingerprint("abc123") is True
        assert state.has_fingerprint("xyz999") is False

    def test_runstate_action_count_increments(self):
        """action_count reflects how many actions have been recorded."""
        state = RunState(max_actions=10, max_tokens=10_000)
        assert state.action_count == 0

        state.record_action(fingerprint="fp1")
        state.record_action(fingerprint="fp2")

        assert state.action_count == 2

    def test_runstate_token_count_accumulates(self):
        """token_count accumulates across multiple record_tokens calls."""
        state = RunState(max_actions=10, max_tokens=10_000)
        state.record_tokens(100)
        state.record_tokens(200)
        assert state.token_count == 300
