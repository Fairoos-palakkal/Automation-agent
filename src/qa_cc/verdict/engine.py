"""VerdictEngine — Deterministic assertion engine.

Establishes ground truth verdicts (PASS, FAIL, INCONCLUSIVE, FLAKY) using deterministic checks only.
CRITICAL INVARIANT: Contains NO LLM dependencies or evaluation agents.
"""
from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional

from qa_cc.verdict.evidence import Verdict, VerdictType


@dataclass
class AssertionRule:
    rule_type: str
    selector: Optional[str] = None
    expected: Optional[str] = None
    pattern: Optional[str] = None


class VerdictEngine:
    """Evaluates rules deterministically against concrete page states."""

    def evaluate(self, rule: AssertionRule, page_state: Dict[str, Any]) -> Verdict:
        html = page_state.get("html", "")
        url = page_state.get("url", "")
        console_errors = page_state.get("console_errors", [])

        # Guard against ambiguous / empty page state
        if not html and not url and not console_errors:
            return Verdict(
                type=VerdictType.INCONCLUSIVE,
                reason="Page state is empty or uninitialized.",
            )

        if rule.rule_type == "url_equals":
            if url == rule.expected:
                return Verdict(
                    type=VerdictType.PASS,
                    reason=f"URL '{url}' matches expected URL.",
                )
            return Verdict(
                type=VerdictType.FAIL,
                reason=f"URL '{url}' does not match expected URL '{rule.expected}'.",
            )

        if rule.rule_type == "no_console_errors":
            pattern = rule.pattern or ".*"
            for err in console_errors:
                err_text = err if isinstance(err, str) else err.get("text", "")
                if re.search(pattern, err_text):
                    return Verdict(
                        type=VerdictType.FAIL,
                        reason=f"Console error matched pattern '{pattern}': {err_text}",
                        details={"error": err_text},
                    )
            return Verdict(
                type=VerdictType.PASS,
                reason="No console errors matched failure pattern.",
            )

        # For element rules, if html is completely blank, return INCONCLUSIVE
        if not html.strip():
            return Verdict(
                type=VerdictType.INCONCLUSIVE,
                reason="HTML body is empty.",
            )

        selector_id = None
        if rule.selector and rule.selector.startswith("#"):
            selector_id = rule.selector[1:]

        if rule.rule_type == "element_exists":
            pattern = rf'id=["\']{selector_id}["\']' if selector_id else re.escape(rule.selector or "")
            if re.search(pattern, html):
                return Verdict(
                    type=VerdictType.PASS,
                    reason=f"Element '{rule.selector}' exists in page.",
                )
            return Verdict(
                type=VerdictType.FAIL,
                reason=f"Element '{rule.selector}' not found in page.",
            )

        if rule.rule_type == "element_contains_text":
            pattern = (
                rf'id=["\']{selector_id}["\'][^>]*>(.*?)<\/'
                if selector_id
                else rf"{re.escape(rule.selector or '')}[^>]*>(.*?)<\/"
            )
            match = re.search(pattern, html, flags=re.DOTALL)
            if not match:
                # Check if element exists at all
                elem_pat = rf'id=["\']{selector_id}["\']' if selector_id else re.escape(rule.selector or "")
                if not re.search(elem_pat, html):
                    return Verdict(
                        type=VerdictType.FAIL,
                        reason=f"Element '{rule.selector}' not found in page.",
                    )
                # Found element, extract inner content
                elem_text = html
            else:
                elem_text = match.group(1)

            if rule.expected and rule.expected in elem_text:
                return Verdict(
                    type=VerdictType.PASS,
                    reason=f"Element '{rule.selector}' matched expected text '{rule.expected}'.",
                )
            return Verdict(
                type=VerdictType.FAIL,
                reason=f"Element '{rule.selector}' did not contain expected text '{rule.expected}'.",
            )

        return Verdict(
            type=VerdictType.INCONCLUSIVE,
            reason=f"Unrecognized rule type '{rule.rule_type}'.",
        )
