"""Tests for FindingVerifier — Phase 7 (T-14)."""
from unittest.mock import MagicMock
import pytest

from qa_cc.verdict.engine import AssertionRule, VerdictEngine
from qa_cc.verdict.evidence import Evidence, EvidenceType, Finding, Verdict, VerdictType
from qa_cc.verdict.replayer import Replayer, ReplayResult
from qa_cc.verdict.verifier import FindingVerifier, derive_assertion_rule
from qa_cc.agents.baseline import RunResult
from qa_cc.report.generator import generate_report


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


class TestFindingVerifier:
    def test_derive_assertion_rule_from_structured_fields(self):
        """T-14: derive_assertion_rule converts structured finding fields to an AssertionRule."""
        # 1. URL finding
        f_url = Finding(
            id="F-1",
            summary="Redirected to wrong page",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<h1>Home</h1>")],
            selector_or_url="http://localhost:3000/cart.html",
        )
        r_url = derive_assertion_rule(f_url)
        assert r_url.rule_type == "url_equals"
        assert r_url.expected == "http://localhost:3000/cart.html"

        # 2. Element text finding
        f_text = Finding(
            id="F-2",
            summary="Cart quantity mismatch",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<div id='cart'>0</div>")],
            selector_or_url="#cart",
            expected="1",
            actual="0",
        )
        r_text = derive_assertion_rule(f_text)
        assert r_text.rule_type == "element_contains_text"
        assert r_text.selector == "#cart"
        assert r_text.expected == "1"

        # 3. Element exists finding
        f_elem = Finding(
            id="F-3",
            summary="Missing buy button",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<div>empty</div>")],
            selector_or_url="button.buy",
        )
        r_elem = derive_assertion_rule(f_elem)
        assert r_elem.rule_type == "element_exists"
        assert r_elem.selector == "button.buy"

        # 4. Console log finding
        f_console = Finding(
            id="F-4",
            summary="TypeError during catalog filter",
            evidence=[Evidence(type=EvidenceType.CONSOLE_LOG, content="TypeError: cannot read property")],
            actual="TypeError: cannot read property",
        )
        r_console = derive_assertion_rule(f_console)
        assert r_console.rule_type == "no_console_errors"
        assert "TypeError" in r_console.pattern

        # 5. Network status code finding
        f_net = Finding(
            id="F-5",
            summary="API returned 500",
            evidence=[Evidence(type=EvidenceType.NETWORK_REQUEST, content="500 Internal Error")],
            expected="200",
            actual="500",
        )
        r_net = derive_assertion_rule(f_net)
        assert r_net.rule_type == "status_code"
        assert r_net.status_code == 200

    def test_finding_verifier_live_assertion_and_replay_confirmed(self):
        """T-14: FindingVerifier executes live assertion and replay, stamping verified FAIL verdict."""
        page = MockPage(html="<div id='count'>-1</div>", url="http://localhost:3000/cart.html")
        context = MockBrowserContext(page)
        browser = MockBrowser(context)
        replayer = Replayer(browser=browser)
        trace_mock = MagicMock()

        verifier = FindingVerifier(
            verdict_engine=VerdictEngine(),
            replayer=replayer,
            trace_writer=trace_mock,
        )

        finding = Finding(
            id="F-10",
            summary="Cart quantity negative",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<div id='count'>-1</div>")],
            selector_or_url="#count",
            expected="Items: 1",
            steps=[{"tool": "navigate", "args": {"url": "http://localhost:3000/cart.html"}}],
        )

        live_state = {"html": "<div id='count'>-1</div>", "url": "http://localhost:3000/cart.html", "console_errors": []}
        verified = verifier.verify_finding(finding, live_page_state=live_state)

        assert verified.verdict is not None
        assert verified.verdict.type == VerdictType.FAIL
        assert "verified" in verified.verdict.reason.lower()
        assert trace_mock.record.called

    def test_finding_verifier_live_assertion_fails_but_replay_passes_downgrades_to_inconclusive(self):
        """T-14: Finding whose assertion passes on fresh replay is stamped INCONCLUSIVE per ADR-0001/0003."""
        # Live state has the bug (html has -1), but replay context is clean/fixed (html has 1)
        page = MockPage(html="<div id='count'>Items: 1</div>", url="http://localhost:3000/cart.html")
        context = MockBrowserContext(page)
        browser = MockBrowser(context)
        replayer = Replayer(browser=browser)

        verifier = FindingVerifier(
            verdict_engine=VerdictEngine(),
            replayer=replayer,
        )

        finding = Finding(
            id="F-11",
            summary="Cart negative defect",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<div id='count'>-1</div>")],
            selector_or_url="#count",
            expected="Items: 1",
            steps=[{"tool": "navigate", "args": {"url": "http://localhost:3000/cart.html"}}],
        )

        live_state = {"html": "<div id='count'>-1</div>", "url": "http://localhost:3000/cart.html", "console_errors": []}
        verified = verifier.verify_finding(finding, live_page_state=live_state)

        assert verified.verdict is not None
        assert verified.verdict.type == VerdictType.INCONCLUSIVE
        assert "downgraded" in verified.verdict.reason.lower()

    def test_report_displays_verdict_reason_step_list_and_trace_link(self, tmp_path):
        """T-14: Report generator displays verdict reason, action step list, and trace link."""
        out_file = tmp_path / "detailed_report.html"
        finding = Finding(
            id="F-102",
            summary="Negative cart balance allowed",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<input value='-5'>")],
            verdict=Verdict(
                type=VerdictType.FAIL,
                reason="Live assertion failed and replay in fresh browser reproduced negative balance",
            ),
            steps=[
                {"tool": "navigate", "args": {"url": "http://localhost:3000/cart.html"}},
                {"tool": "click", "args": {"selector": "#minus"}},
            ],
        )
        result = RunResult(
            findings=[finding],
            actions_count=2,
            tokens_used=80,
            trace_path="runs/baseline/run-001/trace.jsonl",
        )

        generate_report(result, output_path=out_file)
        content = out_file.read_text(encoding="utf-8")

        # 1. Verdict reason is rendered
        assert "Live assertion failed and replay in fresh browser reproduced negative balance" in content
        # 2. Replayable action step list is rendered
        assert "navigate" in content
        assert "http://localhost:3000/cart.html" in content
        assert "click" in content
        assert "#minus" in content
        # 3. Trace link is rendered
        assert "runs/baseline/run-001/trace.jsonl" in content
