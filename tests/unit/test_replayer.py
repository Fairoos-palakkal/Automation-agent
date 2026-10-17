"""Tests for Replayer and Fresh Context Replay — Phase 7 (T-13)."""
from unittest.mock import MagicMock
import pytest

from qa_cc.verdict.engine import AssertionRule, VerdictEngine, finalize_verdict
from qa_cc.verdict.evidence import Evidence, EvidenceType, Finding, Verdict, VerdictType
from qa_cc.verdict.replayer import ReplayResult, Replayer
from qa_cc.agents.challenger import Challenger, ChallengeResult


class MockPage:
    def __init__(self, html: str = "", url: str = "", console_messages=None):
        self._html = html
        self._url = url
        self.console_messages = console_messages or []
        self.actions = []

    def content(self) -> str:
        return self._html

    @property
    def url(self) -> str:
        return self._url

    def goto(self, url: str):
        self._url = url
        self.actions.append(("goto", url))

    def click(self, selector: str):
        self.actions.append(("click", selector))

    def fill(self, selector: str, value: str):
        self.actions.append(("fill", selector, value))


class MockBrowserContext:
    def __init__(self, page: MockPage):
        self.page = page
        self.closed = False

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


class MockBrowser:
    def __init__(self, context: MockBrowserContext):
        self.context = context
        self.context_created = False

    def new_context(self, **kwargs):
        self.context_created = True
        return self.context


class TestReplayer:
    def test_replayer_executes_steps_in_fresh_context(self):
        """T-13: Replayer opens a fresh browser context, runs steps, extracts state, and closes context."""
        page = MockPage(
            html="<div id='cart-count'>-1</div>",
            url="http://localhost:3000/cart.html",
        )
        context = MockBrowserContext(page)
        browser = MockBrowser(context)

        replayer = Replayer(browser=browser)
        steps = [
            {"tool": "navigate", "args": {"url": "http://localhost:3000/cart.html"}},
            {"tool": "click", "args": {"selector": "#minus-btn"}},
        ]

        result = replayer.replay(steps)
        assert result.success is True
        assert browser.context_created is True
        assert context.closed is True
        assert page.actions == [("goto", "http://localhost:3000/cart.html"), ("click", "#minus-btn")]
        assert result.page_state["url"] == "http://localhost:3000/cart.html"
        assert result.page_state["html"] == "<div id='cart-count'>-1</div>"

    def test_replayer_and_evaluate_reproduces_defect(self):
        """T-13: Replayer executes replay and evaluates assertion rule with VerdictEngine."""
        page = MockPage(
            html="<div id='cart-count'>Items: -1</div>",
            url="http://localhost:3000/cart.html",
        )
        context = MockBrowserContext(page)
        browser = MockBrowser(context)

        replayer = Replayer(browser=browser)
        steps = [
            {"tool": "navigate", "args": {"url": "http://localhost:3000/cart.html"}},
            {"tool": "click", "args": {"selector": "#minus-btn"}},
        ]
        # Defect assertion: element with positive count should exist; negative count causes FAIL
        rule = AssertionRule(rule_type="element_contains_text", selector="#cart-count", expected="Items: 1")

        replay_res, verdict = replayer.replay_and_evaluate(steps, rule)
        assert replay_res.success is True
        assert verdict.type == VerdictType.FAIL
        assert "did not contain expected text" in verdict.reason

    def test_replayer_handles_step_error_gracefully(self):
        """T-13: Replayer records failure and closes context if a step raises an error."""
        page = MockPage()

        def faulty_click(selector):
            raise RuntimeError(f"Element {selector} not interactable")

        page.click = faulty_click
        context = MockBrowserContext(page)
        browser = MockBrowser(context)

        replayer = Replayer(browser=browser)
        steps = [
            {"tool": "navigate", "args": {"url": "http://localhost:3000/cart.html"}},
            {"tool": "click", "args": {"selector": "#broken-btn"}},
        ]

        result = replayer.replay(steps)
        assert result.success is False
        assert "not interactable" in str(result.error)
        assert context.closed is True

    def test_challenger_downgrades_when_replay_does_not_reproduce(self):
        """T-13: Challenger downgrades finding to INCONCLUSIVE when replay passes (defect absent)."""
        page = MockPage(
            html="<div id='cart-count'>Items: 1</div>",
            url="http://localhost:3000/cart.html",
        )
        context = MockBrowserContext(page)
        browser = MockBrowser(context)
        replayer = Replayer(browser=browser)

        finding = Finding(
            id="F-10",
            summary="Cart quantity allows negative values",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<div id='cart-count'>Items: -1</div>")],
            steps=[{"tool": "navigate", "args": {"url": "http://localhost:3000/cart.html"}}],
            verdict=Verdict(type=VerdictType.FAIL, reason="Observed -1 count"),
        )
        rule = AssertionRule(rule_type="element_contains_text", selector="#cart-count", expected="Items: 1")

        trace_mock = MagicMock()
        challenger = Challenger(replayer=replayer)
        result = challenger.challenge(finding, assertion_rule=rule, trace_writer=trace_mock)

        assert result.replayed is True
        assert result.reproduced is False
        assert result.final_verdict == VerdictType.INCONCLUSIVE
        assert "not reproduce" in result.reason.lower() or "downgraded" in result.reason.lower()
        assert trace_mock.record.called

    def test_finalize_verdict_combinations(self):
        """T-13/ADR-0003: finalize_verdict combines live assertion and replay deterministically."""
        v_fail = Verdict(type=VerdictType.FAIL, reason="Live assertion failed")
        v_pass = Verdict(type=VerdictType.PASS, reason="Replay assertion passed")
        v_replay_fail = Verdict(type=VerdictType.FAIL, reason="Replay reproduced defect")
        v_flaky = Verdict(type=VerdictType.FLAKY, reason="Intermittent result")

        # 1. Live FAIL + Replay FAIL -> Verified FAIL
        f1 = finalize_verdict(v_fail, v_replay_fail)
        assert f1.type == VerdictType.FAIL
        assert "verified" in f1.reason.lower()

        # 2. Live FAIL + Replay PASS -> Downgraded to INCONCLUSIVE
        f2 = finalize_verdict(v_fail, v_pass)
        assert f2.type == VerdictType.INCONCLUSIVE
        assert "downgraded" in f2.reason.lower()

        # 3. Flaky outcome -> FLAKY
        f3 = finalize_verdict(v_fail, v_flaky)
        assert f3.type == VerdictType.FLAKY

        # 4. No replay available -> INCONCLUSIVE
        f4 = finalize_verdict(v_fail, None)
        assert f4.type == VerdictType.INCONCLUSIVE
