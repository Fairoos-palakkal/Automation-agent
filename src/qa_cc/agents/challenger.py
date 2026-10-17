"""Challenger Agent — Disputes findings by requesting replay and checking evidence (Phase 3.1).

Responsibilities:
- Input is a Finding.
- Verifies that required Evidence is attached and non-empty; if missing/invalid, downgrades to INCONCLUSIVE.
- Requests and executes deterministic replay of recorded steps.
- If replayed steps reproduce the failing assertion, confirms the Finding (FAIL).
- If replayed steps do not reproduce the defect (or pass cleanly), downgrades to INCONCLUSIVE.
- NEVER upgrades a Finding to PASS under any circumstance.
- Never sets a Verdict directly (no set_verdict); relies on VerdictEngine and replay outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qa_cc.gateway.gateway import ToolGateway
from qa_cc.verdict.engine import AssertionRule, VerdictEngine
from qa_cc.verdict.evidence import Finding, VerdictType


@dataclass
class ChallengeResult:
    finding_id: str
    replayed: bool = False
    reproduced: bool = False
    original_verdict: Optional[VerdictType] = None
    final_verdict: Optional[VerdictType] = None
    reason: str = ""
    evidence_valid: bool = True
    details: Dict[str, Any] = field(default_factory=dict)


class Challenger:
    """Disputes Findings by requesting replay and auditing evidence completeness."""

    def __init__(
        self,
        gateway: Optional[ToolGateway] = None,
        verdict_engine: Optional[VerdictEngine] = None,
        replayer: Optional[Any] = None,
        trace_writer: Optional[Any] = None,
    ):
        self.gateway = gateway
        self.verdict_engine = verdict_engine or VerdictEngine()
        self.replayer = replayer
        self.trace_writer = trace_writer

    def can_request_replay(self, finding: Finding) -> bool:
        """Determines if the finding contains actionable recorded steps for replay."""
        return bool(finding.steps and len(finding.steps) > 0)

    def challenge(
        self,
        finding: Finding,
        assertion_rule: Optional[AssertionRule] = None,
        driver: Optional[Any] = None,
        replayer: Optional[Any] = None,
        trace_writer: Optional[Any] = None,
    ) -> ChallengeResult:
        """Challenge a finding by validating evidence and executing deterministic replay.

        Invariants:
        1. Findings with missing/empty evidence are downgraded to INCONCLUSIVE.
        2. A FAIL finding can NEVER be upgraded to PASS.
        3. No access to set_verdict.
        """
        orig_verdict_type = finding.verdict.type if finding.verdict else VerdictType.FAIL
        active_tw = trace_writer or self.trace_writer

        # 1. Audit evidence validity
        if not finding.evidence or len(finding.evidence) == 0:
            res = ChallengeResult(
                finding_id=finding.id,
                replayed=False,
                reproduced=False,
                original_verdict=orig_verdict_type,
                final_verdict=VerdictType.INCONCLUSIVE,
                reason="Finding lacks required Evidence: evidence list is empty.",
                evidence_valid=False,
            )
            if active_tw:
                active_tw.record({
                    "type": "challenger_evaluation",
                    "finding_id": finding.id,
                    "replayed": False,
                    "reproduced": False,
                    "verdict": "INCONCLUSIVE",
                    "reason": res.reason,
                })
            return res

        for ev in finding.evidence:
            if not ev.content or not str(ev.content).strip():
                res = ChallengeResult(
                    finding_id=finding.id,
                    replayed=False,
                    reproduced=False,
                    original_verdict=orig_verdict_type,
                    final_verdict=VerdictType.INCONCLUSIVE,
                    reason="Finding contains invalid Evidence: evidence content is empty or whitespace.",
                    evidence_valid=False,
                )
                if active_tw:
                    active_tw.record({
                        "type": "challenger_evaluation",
                        "finding_id": finding.id,
                        "replayed": False,
                        "reproduced": False,
                        "verdict": "INCONCLUSIVE",
                        "reason": res.reason,
                    })
                return res

        # 2. Check if replay can and should be executed
        active_replayer = replayer or self.replayer
        if not self.can_request_replay(finding) or (not active_replayer and not driver and not self.gateway):
            res = ChallengeResult(
                finding_id=finding.id,
                replayed=False,
                reproduced=False,
                original_verdict=orig_verdict_type,
                final_verdict=orig_verdict_type if orig_verdict_type != VerdictType.PASS else VerdictType.INCONCLUSIVE,
                reason="No replay executed: steps or driver/replayer not available.",
                evidence_valid=True,
            )
            if active_tw:
                active_tw.record({
                    "type": "challenger_evaluation",
                    "finding_id": finding.id,
                    "replayed": False,
                    "reproduced": False,
                    "verdict": res.final_verdict.value if res.final_verdict else None,
                    "reason": res.reason,
                })
            return res

        # 3. Execute replay via Replayer if available
        if active_replayer and assertion_rule:
            replay_res, v = active_replayer.replay_and_evaluate(finding.steps, assertion_rule)
            replayed = True
            reproduced = (v.type == VerdictType.FAIL)
            if not replay_res.success:
                final_v = VerdictType.INCONCLUSIVE
                reason = f"Replay execution failed with error: {replay_res.error}"
            elif reproduced:
                final_v = VerdictType.FAIL
                reason = "Replay successfully reproduced failing check."
            else:
                final_v = VerdictType.INCONCLUSIVE
                reason = f"Replay did not reproduce defect; downgraded to INCONCLUSIVE. ({v.reason})"

            res = ChallengeResult(
                finding_id=finding.id,
                replayed=replayed,
                reproduced=reproduced,
                original_verdict=orig_verdict_type,
                final_verdict=final_v,
                reason=reason,
                evidence_valid=True,
                details=replay_res.page_state,
            )
            if active_tw:
                active_tw.record({
                    "type": "challenger_evaluation",
                    "finding_id": finding.id,
                    "replayed": replayed,
                    "reproduced": reproduced,
                    "verdict": final_v.value,
                    "reason": reason,
                })
            return res

        # Fallback to driver / gateway replay
        replayed = True
        try:
            for step in finding.steps:
                tool = step.get("tool", "")
                args = step.get("args", {})
                if self.gateway:
                    self.gateway.execute(tool, args)
                elif driver:
                    if tool in ("navigate", "goto") and "url" in args:
                        if hasattr(driver, "goto"):
                            driver.goto(args["url"])
                        elif hasattr(driver, "navigate"):
                            driver.navigate(args["url"])
                    elif tool == "click" and "selector" in args:
                        driver.click(args["selector"])
                    elif tool == "fill" and "selector" in args and "value" in args:
                        driver.fill(args["selector"], args["value"])
        except Exception as e:
            res = ChallengeResult(
                finding_id=finding.id,
                replayed=replayed,
                reproduced=False,
                original_verdict=orig_verdict_type,
                final_verdict=VerdictType.INCONCLUSIVE,
                reason=f"Replay execution failed with error: {e}",
                evidence_valid=True,
            )
            if active_tw:
                active_tw.record({
                    "type": "challenger_evaluation",
                    "finding_id": finding.id,
                    "replayed": replayed,
                    "reproduced": False,
                    "verdict": "INCONCLUSIVE",
                    "reason": res.reason,
                })
            return res

        # Evaluate outcome
        page_state = {}
        if driver:
            page_state = {
                "html": driver.content() if hasattr(driver, "content") else getattr(driver, "_html", ""),
                "url": getattr(driver, "url", ""),
                "console_errors": getattr(driver, "console_messages", []),
            }

        reproduced = False
        if assertion_rule:
            v = self.verdict_engine.evaluate(assertion_rule, page_state)
            if v.type == VerdictType.FAIL:
                reproduced = True
        else:
            console_errors = page_state.get("console_errors", [])
            has_error = any(
                (isinstance(err, dict) and err.get("type") == "error") or
                (isinstance(err, str) and "error" in err.lower())
                for err in console_errors
            )
            if has_error:
                reproduced = True

        if reproduced:
            final_v = VerdictType.FAIL
            reason = "Replay successfully reproduced failing check."
        else:
            final_v = VerdictType.INCONCLUSIVE
            reason = "Replay did not reproduce defect; downgraded to INCONCLUSIVE."

        res = ChallengeResult(
            finding_id=finding.id,
            replayed=replayed,
            reproduced=reproduced,
            original_verdict=orig_verdict_type,
            final_verdict=final_v,
            reason=reason,
            evidence_valid=True,
            details=page_state,
        )
        if active_tw:
            active_tw.record({
                "type": "challenger_evaluation",
                "finding_id": finding.id,
                "replayed": replayed,
                "reproduced": reproduced,
                "verdict": final_v.value,
                "reason": reason,
            })
        return res
