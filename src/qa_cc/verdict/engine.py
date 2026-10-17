"""VerdictEngine — Deterministic assertion engine.

Establishes ground truth verdicts (PASS, FAIL, INCONCLUSIVE, FLAKY) using deterministic checks only.
CRITICAL INVARIANT: Contains NO LLM dependencies or evaluation agents.
"""
from dataclasses import dataclass, field
import re
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from qa_cc.verdict.evidence import Verdict, VerdictType


def normalize_url(url: str) -> str:
    """Normalize a URL by trimming trailing slashes on paths and standardizing components."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        path = parts.path
        if path.endswith("/") and len(path) > 1:
            path = path.rstrip("/")
        netloc = parts.netloc.lower()
        return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, parts.fragment))
    except Exception:
        return url.rstrip("/")


@dataclass
class AssertionRule:
    rule_type: str
    selector: Optional[str] = None
    expected: Optional[str] = None
    pattern: Optional[str] = None
    status_code: Optional[int] = None


BENIGN_CONSOLE_PATTERNS = [
    r"favicon\.ico",
    r"\[HMR\]",
    r"\[vite\]",
    r"webpack",
    r"DevTools failed to load source map",
]


class VerdictEngine:
    """Evaluates rules deterministically against concrete page states."""

    def evaluate(self, rule: AssertionRule, page_state: Dict[str, Any]) -> Verdict:
        html = page_state.get("html", "")
        url = page_state.get("url", "")
        console_errors = page_state.get("console_errors", [])
        status_code = page_state.get("status_code")

        # Guard against completely ambiguous / empty page state
        if not html and not url and not console_errors and status_code is None:
            return Verdict(
                type=VerdictType.INCONCLUSIVE,
                reason="Page state is empty or uninitialized.",
            )

        if rule.rule_type == "status_code":
            if status_code is None:
                return Verdict(
                    type=VerdictType.INCONCLUSIVE,
                    reason="Status code not available in page state.",
                )
            if status_code == rule.status_code:
                return Verdict(
                    type=VerdictType.PASS,
                    reason=f"Status code {status_code} matches expected {rule.status_code}.",
                )
            return Verdict(
                type=VerdictType.FAIL,
                reason=f"Status code {status_code} does not match expected {rule.status_code}.",
            )

        if rule.rule_type == "url_equals":
            norm_actual = normalize_url(url)
            norm_expected = normalize_url(rule.expected or "")
            if norm_actual == norm_expected:
                return Verdict(
                    type=VerdictType.PASS,
                    reason=f"URL '{url}' matches expected URL '{rule.expected}'.",
                )
            return Verdict(
                type=VerdictType.FAIL,
                reason=f"URL '{url}' does not match expected URL '{rule.expected}'.",
            )

        if rule.rule_type == "no_console_errors":
            pattern = rule.pattern
            for err in console_errors:
                if isinstance(err, dict):
                    err_text = err.get("text", "")
                    err_type = err.get("type", "error")
                    if err_type in ("log", "info", "debug", "dir"):
                        continue
                else:
                    err_text = str(err)

                # Skip benign noise unless specifically targeted by an explicit pattern
                is_benign = any(re.search(bp, err_text, re.IGNORECASE) for bp in BENIGN_CONSOLE_PATTERNS)
                if is_benign and (not pattern or "favicon" not in pattern.lower()):
                    continue

                if pattern and pattern != ".*":
                    if re.search(pattern, err_text):
                        return Verdict(
                            type=VerdictType.FAIL,
                            reason=f"Console error matched pattern '{pattern}': {err_text}",
                            details={"error": err_text},
                        )
                else:
                    # Treat any non-benign error message as failure
                    if "error" in err_text.lower() or "uncaught" in err_text.lower() or "exception" in err_text.lower():
                        return Verdict(
                            type=VerdictType.FAIL,
                            reason=f"Uncaught console error detected: {err_text}",
                            details={"error": err_text},
                        )

            return Verdict(
                type=VerdictType.PASS,
                reason="No console errors matched failure pattern.",
            )

        # Element rules require non-blank HTML
        if not html or not html.strip():
            return Verdict(
                type=VerdictType.INCONCLUSIVE,
                reason="HTML body is empty.",
            )

        soup = BeautifulSoup(html, "html.parser")
        selector = (rule.selector or "").strip()

        if rule.rule_type == "element_exists":
            matched = False
            if selector:
                try:
                    elements = soup.select(selector)
                    matched = len(elements) > 0
                except Exception:
                    # Fallback for simple ID selectors if CSS parser errors
                    if selector.startswith("#"):
                        matched = soup.find(id=selector[1:]) is not None
                    else:
                        matched = selector in html
            if matched:
                return Verdict(
                    type=VerdictType.PASS,
                    reason=f"Element '{rule.selector}' exists in page.",
                )
            return Verdict(
                type=VerdictType.FAIL,
                reason=f"Element '{rule.selector}' not found in page.",
            )

        if rule.rule_type == "element_contains_text":
            elements = []
            if selector:
                try:
                    elements = soup.select(selector)
                except Exception:
                    if selector.startswith("#"):
                        el = soup.find(id=selector[1:])
                        if el:
                            elements = [el]

                if not elements:
                    return Verdict(
                        type=VerdictType.FAIL,
                        reason=f"Element '{rule.selector}' not found in page.",
                    )
            else:
                elements = [soup]

            expected = rule.expected or ""
            # Inspect full inner text across nested DOM children
            for el in elements:
                full_text = el.get_text()
                if expected in full_text:
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

    def evaluate_with_retry(
        self,
        rule: AssertionRule,
        page_state: Optional[Dict[str, Any]] = None,
        state_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        states: Optional[List[Dict[str, Any]]] = None,
        retries: int = 3,
    ) -> Verdict:
        """Evaluate an AssertionRule across multiple states or invocations to detect FLAKY behavior."""
        verdicts: List[Verdict] = []

        if states is not None:
            for s in states[:retries]:
                verdicts.append(self.evaluate(rule, s))
        elif state_fn is not None:
            for _ in range(retries):
                verdicts.append(self.evaluate(rule, state_fn()))
        elif page_state is not None:
            for _ in range(retries):
                verdicts.append(self.evaluate(rule, page_state))
        else:
            return Verdict(type=VerdictType.INCONCLUSIVE, reason="No page state or state provider supplied for retry.")

        if not verdicts:
            return Verdict(type=VerdictType.INCONCLUSIVE, reason="No retry evaluations were executed.")

        types = [v.type for v in verdicts]
        unique_types = set(types)

        if len(unique_types) == 1:
            return verdicts[0]

        # Inconsistent retry outcomes are labeled FLAKY
        reasons = [f"Attempt {i+1}: {v.type.value} ({v.reason})" for i, v in enumerate(verdicts)]
        return Verdict(
            type=VerdictType.FLAKY,
            reason=f"Assertion was inconsistent across retries: {[t.value for t in types]} (FLAKY)",
            details={"history": [t.value for t in types], "attempts": reasons},
        )


def finalize_verdict(
    live_verdict: Optional[Verdict],
    replay_verdict: Optional[Union[Verdict, Any]],
) -> Verdict:
    """Deterministically compute final verdict from live assertion and fresh-context replay.

    Invariants (ADR-0001, ADR-0003):
    1. If replay reproduced the failure (both live and replay are FAIL) -> FAIL.
    2. If live failed but replay passed (non-reproducible) -> INCONCLUSIVE.
    3. If either outcome is FLAKY -> FLAKY.
    4. If replay is absent/incomplete -> INCONCLUSIVE.
    5. Never upgrades a finding to PASS.
    """
    if not live_verdict:
        return Verdict(
            type=VerdictType.INCONCLUSIVE,
            reason="No live assertion verdict available.",
        )

    if live_verdict.type == VerdictType.FLAKY:
        return Verdict(
            type=VerdictType.FLAKY,
            reason=f"Live assertion was flaky: {live_verdict.reason}",
            details=live_verdict.details,
        )

    if replay_verdict is None:
        return Verdict(
            type=VerdictType.INCONCLUSIVE,
            reason="No replay execution available to verify finding.",
        )

    replay_type = getattr(replay_verdict, "type", None) or getattr(replay_verdict, "final_verdict", None)
    replay_reason = getattr(replay_verdict, "reason", "")

    if replay_type == VerdictType.FLAKY:
        return Verdict(
            type=VerdictType.FLAKY,
            reason=f"Replay assertion outcome was flaky: {replay_reason}",
            details=getattr(replay_verdict, "details", {}),
        )

    if live_verdict.type == VerdictType.FAIL:
        if replay_type == VerdictType.FAIL:
            return Verdict(
                type=VerdictType.FAIL,
                reason="Defect verified by live assertion and fresh-context replay.",
                details={"live_reason": live_verdict.reason, "replay_reason": replay_reason},
            )
        else:
            return Verdict(
                type=VerdictType.INCONCLUSIVE,
                reason=f"Live check failed but fresh-context replay passed; downgraded to INCONCLUSIVE per ADR-0001/ADR-0003. ({replay_reason})",
                details={"live_reason": live_verdict.reason, "replay_reason": replay_reason},
            )

    if live_verdict.type == VerdictType.PASS:
        return Verdict(
            type=VerdictType.INCONCLUSIVE,
            reason=f"Live check passed; finding was not reproducible. ({live_verdict.reason})",
        )

    return Verdict(
        type=VerdictType.INCONCLUSIVE,
        reason=f"Inconclusive verdict pipeline outcome. (Live: {live_verdict.reason}, Replay: {replay_reason})",
    )


