"""Replayer — Deterministic step re-execution in isolated browser contexts (Phase 7, T-13).

Invariants (ADR-0001, ADR-0003, PRD §6):
1. Executes recorded action steps from StepLog / finding.steps within a fresh, isolated browser context.
2. Context is always closed in a finally block to prevent resource leaks.
3. Evaluates reproduction deterministically via VerdictEngine.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from qa_cc.trace.writer import TraceWriter
from qa_cc.verdict.engine import AssertionRule, VerdictEngine
from qa_cc.verdict.evidence import Verdict, VerdictType


@dataclass
class ReplayResult:
    success: bool
    page_state: Dict[str, Any] = field(default_factory=dict)
    replayed_steps: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


class Replayer:
    """Replays recorded action steps inside a clean, fresh browser context."""

    def __init__(
        self,
        browser: Optional[Any] = None,
        driver: Optional[Any] = None,
        allowlist: Optional[List[str]] = None,
        trace_writer: Optional[TraceWriter] = None,
        verdict_engine: Optional[VerdictEngine] = None,
    ):
        self.browser = browser
        self.driver = driver
        self.allowlist = allowlist
        self.trace_writer = trace_writer
        self.verdict_engine = verdict_engine or VerdictEngine()

    def replay(
        self,
        steps: List[Dict[str, Any]],
        target_url: Optional[str] = None,
    ) -> ReplayResult:
        """Re-execute a sequence of action steps inside a fresh context."""
        if not steps:
            return ReplayResult(
                success=False,
                error="No steps provided for replay.",
            )

        if self.browser:
            context = self.browser.new_context()
            console_messages: List[Any] = []
            try:
                page = context.new_page()
                if hasattr(page, "on"):
                    page.on("console", lambda msg: console_messages.append({"type": getattr(msg, "type", "log"), "text": getattr(msg, "text", str(msg))}))
                    page.on("pageerror", lambda err: console_messages.append({"type": "error", "text": f"Uncaught exception: {err}"}))

                replayed: List[Dict[str, Any]] = []
                for step in steps:
                    tool = step.get("tool", "")
                    args = step.get("args", {})
                    if tool in ("navigate", "goto") and "url" in args:
                        page.goto(args["url"])
                        replayed.append(step)
                    elif tool == "click" and "selector" in args:
                        page.click(args["selector"])
                        replayed.append(step)
                    elif tool == "fill" and "selector" in args and "value" in args:
                        page.fill(args["selector"], args["value"])
                        replayed.append(step)

                page_state = {
                    "html": page.content() if hasattr(page, "content") else "",
                    "url": page.url if hasattr(page, "url") else "",
                    "console_errors": console_messages,
                }
                return ReplayResult(
                    success=True,
                    page_state=page_state,
                    replayed_steps=replayed,
                )
            except Exception as e:
                return ReplayResult(
                    success=False,
                    page_state={"html": "", "url": "", "console_errors": console_messages},
                    replayed_steps=[],
                    error=str(e),
                )
            finally:
                try:
                    context.close()
                except Exception:
                    pass

        elif self.driver:
            replayed = []
            try:
                for step in steps:
                    tool = step.get("tool", "")
                    args = step.get("args", {})
                    if tool in ("navigate", "goto") and "url" in args:
                        if hasattr(self.driver, "goto"):
                            self.driver.goto(args["url"])
                        elif hasattr(self.driver, "navigate"):
                            self.driver.navigate(args["url"])
                        replayed.append(step)
                    elif tool == "click" and "selector" in args:
                        self.driver.click(args["selector"])
                        replayed.append(step)
                    elif tool == "fill" and "selector" in args and "value" in args:
                        self.driver.fill(args["selector"], args["value"])
                        replayed.append(step)

                page_state = {
                    "html": self.driver.content() if hasattr(self.driver, "content") else getattr(self.driver, "_html", ""),
                    "url": getattr(self.driver, "url", ""),
                    "console_errors": getattr(self.driver, "console_messages", []),
                }
                return ReplayResult(
                    success=True,
                    page_state=page_state,
                    replayed_steps=replayed,
                )
            except Exception as e:
                return ReplayResult(
                    success=False,
                    page_state={"html": "", "url": getattr(self.driver, "url", ""), "console_errors": []},
                    replayed_steps=[],
                    error=str(e),
                )

        return ReplayResult(
            success=False,
            error="No browser or driver configured for Replayer.",
        )

    def replay_and_evaluate(
        self,
        steps: List[Dict[str, Any]],
        rule: AssertionRule,
        target_url: Optional[str] = None,
    ) -> Tuple[ReplayResult, Verdict]:
        """Replay steps in fresh context and evaluate an AssertionRule."""
        replay_res = self.replay(steps, target_url=target_url)
        if not replay_res.success:
            return replay_res, Verdict(
                type=VerdictType.INCONCLUSIVE,
                reason=f"Replay execution failed: {replay_res.error}",
            )

        verdict = self.verdict_engine.evaluate(rule, replay_res.page_state)
        return replay_res, verdict
