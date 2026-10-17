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

    @pytest.mark.parametrize(
        "selector,html,expected_verdict",
        [
            ("button.buy", "<button class='buy'>Buy Now</button>", VerdictType.PASS),
            (".buy", "<a href='#' class='btn buy'>Click</a>", VerdictType.PASS),
            ("[data-testid='add-cart']", "<button data-testid='add-cart'>Add</button>", VerdictType.PASS),
            ("div.cart > span.badge", "<div class='cart'><span class='badge'>2</span></div>", VerdictType.PASS),
            ("button.buy", "<button class='cancel'>Cancel</button>", VerdictType.FAIL),
            (".nonexistent-class", "<div>Plain content</div>", VerdictType.FAIL),
        ],
    )
    def test_element_exists_real_css_selectors(self, selector, html, expected_verdict):
        """T-12: element_exists evaluates real CSS selectors including classes, attributes, and hierarchies."""
        engine = VerdictEngine()
        rule = AssertionRule(rule_type="element_exists", selector=selector)
        page_state = {"html": html, "url": "http://localhost:3000/cart.html", "console_errors": []}
        verdict = engine.evaluate(rule, page_state)
        assert verdict.type == expected_verdict

    @pytest.mark.parametrize(
        "expected_url,actual_url,expected_verdict",
        [
            ("http://localhost:3000/cart", "http://localhost:3000/cart/", VerdictType.PASS),
            ("http://localhost:3000/catalog/", "http://localhost:3000/catalog", VerdictType.PASS),
            ("http://localhost:3000/index.html/", "http://localhost:3000/index.html", VerdictType.PASS),
            ("http://localhost:3000/cart", "http://localhost:3000/checkout", VerdictType.FAIL),
        ],
    )
    def test_url_equals_trailing_slash_normalization(self, expected_url, actual_url, expected_verdict):
        """T-12: url_equals normalizes trailing slashes to prevent false failures."""
        engine = VerdictEngine()
        rule = AssertionRule(rule_type="url_equals", expected=expected_url)
        page_state = {"html": "<div>ok</div>", "url": actual_url, "console_errors": []}
        verdict = engine.evaluate(rule, page_state)
        assert verdict.type == expected_verdict

    def test_element_contains_text_nested_markup(self):
        """T-12: element_contains_text inspects full inner text across nested DOM children."""
        engine = VerdictEngine()
        rule = AssertionRule(
            rule_type="element_contains_text",
            selector="div.order-summary",
            expected="Total: $49.99",
        )
        html = (
            "<div class='order-summary'>"
            "  <h2>Order Summary</h2>"
            "  <div class='total-line'><span>Total: </span><b>$49.99</b></div>"
            "</div>"
        )
        page_state = {"html": html, "url": "http://localhost:3000/checkout.html", "console_errors": []}
        verdict = engine.evaluate(rule, page_state)
        assert verdict.type == VerdictType.PASS
        assert "matched expected text" in verdict.reason

    def test_status_code_rule(self):
        """T-12: status_code rule asserts HTTP response status code deterministically."""
        engine = VerdictEngine()
        rule_200 = AssertionRule(rule_type="status_code", status_code=200)
        rule_500 = AssertionRule(rule_type="status_code", status_code=500)

        # 200 matches
        v1 = engine.evaluate(rule_200, {"status_code": 200, "html": "", "url": "http://localhost:3000/api"})
        assert v1.type == VerdictType.PASS

        # 200 mismatches 500
        v2 = engine.evaluate(rule_200, {"status_code": 500, "html": "", "url": "http://localhost:3000/api"})
        assert v2.type == VerdictType.FAIL
        assert "500" in v2.reason

        # Missing status_code is INCONCLUSIVE
        v3 = engine.evaluate(rule_500, {"html": "<div>no status</div>", "url": "http://localhost:3000"})
        assert v3.type == VerdictType.INCONCLUSIVE

    def test_no_console_errors_ignores_benign_messages(self):
        """T-12: no_console_errors ignores benign messages such as favicon 404 or informational logs."""
        engine = VerdictEngine()
        rule = AssertionRule(rule_type="no_console_errors")

        # Benign favicon 404 does NOT cause FAIL
        page_state_benign = {
            "html": "<div>Safe</div>",
            "url": "http://localhost:3000",
            "console_errors": [
                "Failed to load resource: the server responded with a status of 404 (favicon.ico)",
                "[HMR] connected",
            ],
        }
        v_benign = engine.evaluate(rule, page_state_benign)
        assert v_benign.type == VerdictType.PASS

        # Actual uncaught exception causes FAIL
        page_state_real_err = {
            "html": "<div>Crash</div>",
            "url": "http://localhost:3000",
            "console_errors": [
                "Uncaught TypeError: Cannot read property 'map' of undefined",
            ],
        }
        v_err = engine.evaluate(rule, page_state_real_err)
        assert v_err.type == VerdictType.FAIL

    def test_evaluate_with_retry_flaky_and_pass(self):
        """T-12: evaluate_with_retry returns FLAKY when retry outcomes differ, and PASS when consistent."""
        engine = VerdictEngine()
        rule = AssertionRule(rule_type="element_exists", selector="button.buy")

        state_fail = {"html": "<div>no button yet</div>", "url": "http://localhost:3000", "console_errors": []}
        state_pass = {"html": "<button class='buy'>Buy</button>", "url": "http://localhost:3000", "console_errors": []}

        # Sequence of states: fail on attempt 1, pass on attempt 2 -> FLAKY
        states_flaky = [state_fail, state_pass]
        v_flaky = engine.evaluate_with_retry(rule, states=states_flaky, retries=2)
        assert v_flaky.type == VerdictType.FLAKY
        assert "flaky" in v_flaky.reason.lower() or "inconsistent" in v_flaky.reason.lower()

        # Consistent PASS sequence
        v_pass = engine.evaluate_with_retry(rule, states=[state_pass, state_pass], retries=2)
        assert v_pass.type == VerdictType.PASS

        # Consistent FAIL sequence
        v_fail = engine.evaluate_with_retry(rule, states=[state_fail, state_fail], retries=2)
        assert v_fail.type == VerdictType.FAIL

