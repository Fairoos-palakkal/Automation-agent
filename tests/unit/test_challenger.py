"""Tests for Challenger Agent — Phase 3.1 (Red -> Green)."""
import ast
from pathlib import Path
import pytest

from qa_cc.agents.challenger import Challenger, ChallengeResult
from qa_cc.verdict.engine import AssertionRule, VerdictEngine
from qa_cc.verdict.evidence import Evidence, EvidenceType, Finding, Verdict, VerdictType

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class MockDriver:
    def __init__(self, html: str = "", url: str = "", console_messages=None):
        self._html = html
        self.url = url
        self.console_messages = console_messages or []
        self.actions = []

    def content(self) -> str:
        return self._html

    def goto(self, url: str):
        self.url = url
        self.actions.append(("navigate", url))

    def navigate(self, url: str):
        self.goto(url)

    def click(self, selector: str):
        self.actions.append(("click", selector))

    def fill(self, selector: str, value: str):
        self.actions.append(("fill", selector, value))


class TestChallenger:
    def test_challenger_can_request_replay(self):
        """Given a Finding with recorded steps, Challenger requests replay."""
        finding = Finding(
            id="F-1",
            summary="Cart quantity allows negative values",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<input value='-1'>")],
            steps=[
                {"tool": "navigate", "args": {"url": "http://localhost:3000/cart.html"}},
                {"tool": "click", "args": {"selector": "#btn-minus"}},
            ],
        )
        challenger = Challenger()
        assert challenger.can_request_replay(finding) is True

        # Finding with no steps cannot be replayed
        finding_no_steps = Finding(
            id="F-1b",
            summary="Cart defect with no steps",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<input value='-1'>")],
            steps=[],
        )
        assert challenger.can_request_replay(finding_no_steps) is False

    def test_challenger_downgrades_to_inconclusive(self):
        """Finding with missing Evidence is downgraded to INCONCLUSIVE."""
        # Bypass pydantic validation using model_construct to simulate malformed/empty evidence
        finding_empty_evidence = Finding.model_construct(
            id="F-2",
            summary="Broken checkout button",
            evidence=[],
            verdict=Verdict(type=VerdictType.FAIL, reason="Button unclickable"),
            steps=[],
        )
        challenger = Challenger()
        result = challenger.challenge(finding_empty_evidence)
        assert result.final_verdict == VerdictType.INCONCLUSIVE
        assert result.evidence_valid is False
        assert "evidence" in result.reason.lower()

        # Finding with whitespace-only content in Evidence
        finding_blank_evidence = Finding(
            id="F-2b",
            summary="Broken checkout button",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="   ")],
            verdict=Verdict(type=VerdictType.FAIL, reason="Button unclickable"),
        )
        result_blank = challenger.challenge(finding_blank_evidence)
        assert result_blank.final_verdict == VerdictType.INCONCLUSIVE
        assert result_blank.evidence_valid is False

    def test_challenger_never_upgrades(self):
        """A FAIL Finding cannot become PASS through Challenger."""
        finding = Finding(
            id="F-3",
            summary="Catalog filter error",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<div id='catalog'></div>")],
            verdict=Verdict(type=VerdictType.FAIL, reason="Original failure observed"),
            steps=[{"tool": "navigate", "args": {"url": "http://localhost:3000/catalog.html"}}],
        )
        # Driver where assertion cleanly passes (e.g., no error observed during replay)
        driver = MockDriver(
            html="<div id='catalog'>Catalog Content</div>",
            url="http://localhost:3000/catalog.html",
            console_messages=[],
        )
        rule = AssertionRule(rule_type="element_exists", selector="#catalog")

        challenger = Challenger()
        result = challenger.challenge(finding, assertion_rule=rule, driver=driver)

        # Under no circumstance may FAIL be upgraded to PASS
        assert result.final_verdict != VerdictType.PASS
        assert result.final_verdict == VerdictType.INCONCLUSIVE
        assert "not reproduced" in result.reason.lower() or "replay" in result.reason.lower()

    def test_challenger_never_sets_verdict(self):
        """Challenger has no access to VerdictEngine.set_verdict() and provides no set_verdict."""
        challenger = Challenger()
        assert not hasattr(challenger, "set_verdict"), "Challenger must not provide set_verdict"
        assert not hasattr(VerdictEngine, "set_verdict"), "VerdictEngine must not provide set_verdict"

        # AST inspection: verify Challenger code never defines or calls set_verdict
        challenger_file = REPO_ROOT / "src" / "qa_cc" / "agents" / "challenger.py"
        assert challenger_file.exists(), "challenger.py must exist"
        tree = ast.parse(challenger_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert node.name != "set_verdict", f"Forbidden method set_verdict defined in {challenger_file}"
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "set_verdict":
                    pytest.fail(f"Forbidden call to set_verdict in {challenger_file}")

    def test_replay_reproduces_failing_check(self):
        """Replayed steps hit the same assertion -> confirms Finding as FAIL."""
        finding = Finding(
            id="F-5",
            summary="Filter unhandled TypeError",
            evidence=[Evidence(type=EvidenceType.CONSOLE_LOG, content="TypeError: undefined")],
            verdict=Verdict(type=VerdictType.FAIL, reason="Console error on filter"),
            steps=[
                {"tool": "navigate", "args": {"url": "http://localhost:3000/catalog.html"}},
                {"tool": "click", "args": {"selector": "#btn-filter"}},
            ],
        )
        driver = MockDriver(
            html="<div id='catalog'>Catalog</div>",
            url="http://localhost:3000/catalog.html",
            console_messages=[{"type": "error", "text": "TypeError: Cannot read properties of undefined"}],
        )
        rule = AssertionRule(rule_type="no_console_errors", pattern="TypeError.*")

        challenger = Challenger()
        result = challenger.challenge(finding, assertion_rule=rule, driver=driver)

        assert result.replayed is True
        assert result.reproduced is True
        assert result.final_verdict == VerdictType.FAIL
        assert ("navigate", "http://localhost:3000/catalog.html") in driver.actions
        assert ("click", "#btn-filter") in driver.actions
