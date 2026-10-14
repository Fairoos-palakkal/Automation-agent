"""Tests for VerdictEngine — Phase 1.4 (Red -> Green)."""
import ast
from pathlib import Path
import pytest

from qa_cc.verdict.engine import VerdictEngine, AssertionRule
from qa_cc.verdict.evidence import VerdictType, Finding, Evidence, EvidenceType

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestVerdictEngine:
    def test_verdict_pass_when_element_has_expected_state(self):
        """Element present with expected text returns PASS."""
        engine = VerdictEngine()
        rule = AssertionRule(
            rule_type="element_contains_text",
            selector="#welcome",
            expected="Welcome to Acme",
        )
        page_state = {
            "html": "<div id='welcome'>Welcome to Acme Store</div>",
            "url": "http://localhost:3000/index.html",
            "console_errors": [],
        }

        verdict = engine.evaluate(rule, page_state)
        assert verdict.type == VerdictType.PASS
        assert "matched expected text" in verdict.reason

    def test_verdict_fail_when_element_missing(self):
        """Expected element absent returns FAIL."""
        engine = VerdictEngine()
        rule = AssertionRule(
            rule_type="element_exists",
            selector="#email-error",
        )
        page_state = {
            "html": "<form><input id='email'/></form>",
            "url": "http://localhost:3000/contact.html",
            "console_errors": [],
        }

        verdict = engine.evaluate(rule, page_state)
        assert verdict.type == VerdictType.FAIL
        assert "not found" in verdict.reason

    def test_verdict_fail_on_unexpected_url(self):
        """Page URL not matching expected URL returns FAIL."""
        engine = VerdictEngine()
        rule = AssertionRule(
            rule_type="url_equals",
            expected="http://localhost:3000/pricing.html",
        )
        page_state = {
            "html": "<h1>404 Not Found</h1>",
            "url": "http://localhost:3000/pricing-old.html",
            "console_errors": [],
        }

        verdict = engine.evaluate(rule, page_state)
        assert verdict.type == VerdictType.FAIL
        assert "does not match" in verdict.reason

    def test_verdict_fail_on_console_error(self):
        """Console errors matching a failure pattern return FAIL."""
        engine = VerdictEngine()
        rule = AssertionRule(
            rule_type="no_console_errors",
            pattern="TypeError.*",
        )
        page_state = {
            "html": "<div>Catalog</div>",
            "url": "http://localhost:3000/catalog.html",
            "console_errors": ["TypeError: Cannot read properties of undefined"],
        }

        verdict = engine.evaluate(rule, page_state)
        assert verdict.type == VerdictType.FAIL
        assert "Console error matched pattern" in verdict.reason

    def test_verdict_inconclusive_on_ambiguous_state(self):
        """Ambiguous or incomplete page state returns INCONCLUSIVE."""
        engine = VerdictEngine()
        rule = AssertionRule(
            rule_type="element_contains_text",
            selector="#dynamic-result",
            expected="Confirmed",
        )
        # Empty or broken page state
        page_state = {
            "html": "",
            "url": "about:blank",
            "console_errors": [],
        }

        verdict = engine.evaluate(rule, page_state)
        assert verdict.type == VerdictType.INCONCLUSIVE

    def test_verdict_never_set_by_llm(self):
        """Architecture invariant: VerdictEngine must not import or depend on LLM modules."""
        engine_file = REPO_ROOT / "src" / "qa_cc" / "verdict" / "engine.py"
        assert engine_file.exists()

        tree = ast.parse(engine_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "llm" not in alias.name, f"Forbidden LLM import in VerdictEngine: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "llm" not in module, f"Forbidden LLM from-import in VerdictEngine: {module}"
