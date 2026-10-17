"""FindingVerifier — Derives assertions and verifies findings via engine and replay (Phase 7, T-14).

Invariants (ADR-0001, ADR-0003, PRD §6):
1. Derives an AssertionRule from structured finding fields and captured observations.
2. Evaluates the rule against live state via VerdictEngine.
3. Replays steps in a fresh, isolated browser context via Replayer / Challenger.
4. Determines final verdict via finalize_verdict (PASS, FAIL, INCONCLUSIVE, FLAKY).
5. Writes verified verdict and reason to the finding and trace.jsonl.
6. Contains NO LLM dependencies and never upgrades a finding to PASS.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from qa_cc.agents.challenger import Challenger, ChallengeResult
from qa_cc.trace.writer import TraceWriter
from qa_cc.verdict.engine import AssertionRule, VerdictEngine, finalize_verdict
from qa_cc.verdict.evidence import EvidenceType, Finding, Verdict, VerdictType
from qa_cc.verdict.replayer import Replayer


def derive_assertion_rule(finding: Finding) -> AssertionRule:
    """Derive a deterministic AssertionRule from structured finding fields."""
    summary = finding.summary or ""
    expected = finding.expected or ""
    actual = finding.actual or ""
    selector_or_url = finding.selector_or_url or ""

    # Check evidence types
    evidence_types = [ev.type for ev in finding.evidence]

    # 1. Console errors
    if EvidenceType.CONSOLE_LOG in evidence_types:
        pattern = actual or summary
        # If error has a specific exception class like TypeError, SyntaxError, etc.
        match = re.search(r"(\w*Error)", pattern)
        if match:
            err_class = match.group(1)
            return AssertionRule(rule_type="no_console_errors", pattern=f"{err_class}.*")
        return AssertionRule(rule_type="no_console_errors", pattern=pattern or ".*")

    # 2. HTTP Network status code checks
    if EvidenceType.NETWORK_REQUEST in evidence_types:
        code_match = re.search(r"\b([1-5]\d\d)\b", expected)
        if code_match:
            status_code = int(code_match.group(1))
            return AssertionRule(rule_type="status_code", status_code=status_code)
        if expected.strip().isdigit():
            return AssertionRule(rule_type="status_code", status_code=int(expected.strip()))

    # 3. URL equality checks
    if selector_or_url.startswith("http://") or selector_or_url.startswith("https://"):
        return AssertionRule(rule_type="url_equals", expected=selector_or_url)

    # 4. Element text assertions
    if expected:
        return AssertionRule(
            rule_type="element_contains_text",
            selector=selector_or_url or None,
            expected=expected,
        )

    # 5. Element presence checks
    if selector_or_url:
        return AssertionRule(rule_type="element_exists", selector=selector_or_url)

    # Fallback to general element presence
    return AssertionRule(rule_type="element_exists", selector="body")


class FindingVerifier:
    """Verifies findings by combining live assertions with fresh-context replay."""

    def __init__(
        self,
        verdict_engine: Optional[VerdictEngine] = None,
        replayer: Optional[Replayer] = None,
        challenger: Optional[Challenger] = None,
        trace_writer: Optional[TraceWriter] = None,
    ):
        self.verdict_engine = verdict_engine or VerdictEngine()
        self.replayer = replayer
        self.challenger = challenger or Challenger(
            verdict_engine=self.verdict_engine,
            replayer=self.replayer,
            trace_writer=trace_writer,
        )
        self.trace_writer = trace_writer

    def verify_finding(
        self,
        finding: Finding,
        live_page_state: Optional[Dict[str, Any]] = None,
        rule: Optional[AssertionRule] = None,
    ) -> Finding:
        """Execute the deterministic verdict pipeline for a single Finding."""
        active_rule = rule or derive_assertion_rule(finding)

        # Step 1: Live assertion check
        if live_page_state:
            live_v = self.verdict_engine.evaluate(active_rule, live_page_state)
        else:
            # Reconstruct plausible state from captured observations
            dom_ev = next((ev for ev in finding.evidence if ev.type == EvidenceType.DOM_SNAPSHOT), None)
            console_ev = next((ev for ev in finding.evidence if ev.type == EvidenceType.CONSOLE_LOG), None)
            net_ev = next((ev for ev in finding.evidence if ev.type == EvidenceType.NETWORK_REQUEST), None)

            syn_state: Dict[str, Any] = {}
            if dom_ev:
                syn_state["html"] = dom_ev.content
                syn_state["url"] = dom_ev.metadata.get("url", "")
            if console_ev:
                syn_state["console_errors"] = [console_ev.content]
            if net_ev:
                code_match = re.search(r"\b([1-5]\d\d)\b", net_ev.content)
                if code_match:
                    syn_state["status_code"] = int(code_match.group(1))

            if syn_state:
                live_v = self.verdict_engine.evaluate(active_rule, syn_state)
            else:
                live_v = Verdict(
                    type=VerdictType.FAIL,
                    reason="Defect reported with concrete evidence but live state uncaptured.",
                )

        # Step 2: Fresh-context replay via Challenger / Replayer
        if self.replayer:
            challenge_res = self.challenger.challenge(
                finding,
                assertion_rule=active_rule,
                replayer=self.replayer,
                trace_writer=self.trace_writer,
            )
            final_v = finalize_verdict(live_v, challenge_res)
        else:
            final_v = finalize_verdict(live_v, None)

        # Step 3: Stamp final deterministic verdict on Finding
        finding.verdict = final_v

        # Step 4: Record in trace
        if self.trace_writer:
            self.trace_writer.record({
                "type": "finding_verified",
                "finding_id": finding.id,
                "rule_type": active_rule.rule_type,
                "selector": active_rule.selector,
                "expected": active_rule.expected,
                "live_verdict": live_v.type.value if live_v else None,
                "verdict": final_v.type.value,
                "reason": final_v.reason,
            })

        return finding

    def verify_findings(
        self,
        findings: List[Finding],
        live_page_state: Optional[Dict[str, Any]] = None,
    ) -> List[Finding]:
        """Verify all findings in batch."""
        return [self.verify_finding(f, live_page_state=live_page_state) for f in findings]
