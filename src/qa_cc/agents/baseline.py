"""BaselineAgent — Single autonomous QA agent for Day 1 exploration, evidence capture, and findings generation."""
from dataclasses import dataclass, field
import json
from typing import Any, Dict, List, Optional

from qa_cc.agents.loop_detector import (
    LoopDetector,
    RecoveryAction,
    compute_action_fingerprint,
    compute_observation_fingerprint,
)
from qa_cc.gateway.gateway import ToolGateway
from qa_cc.llm.client import LLMClient
from qa_cc.trace.run_state import RunState, BudgetExceeded
from qa_cc.trace.writer import TraceWriter
from qa_cc.verdict.engine import VerdictEngine
from qa_cc.verdict.evidence import Evidence, EvidenceType, Finding


@dataclass
class RunResult:
    findings: List[Finding] = field(default_factory=list)
    actions_count: int = 0
    tokens_used: int = 0
    budget_exceeded: bool = False
    loop_recovery_triggered: bool = False
    trace_path: Optional[str] = None
    summary: str = ""


DEFAULT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Navigate to a URL on the target site and receive a compacted DOM snapshot.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "Target page URL"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click an interactive element matching a CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string", "description": "CSS selector to click"}},
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fill",
            "description": "Fill a form input field matching a CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of input"},
                    "value": {"type": "string", "description": "Value to enter"},
                },
                "required": ["selector", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Capture a screenshot Evidence of the current browser page.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Artifact output path for image"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_finding",
            "description": "Record a discovered software bug, visual error, broken link, or unexpected state with evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Summary of the defect"},
                    "evidence_type": {"type": "string", "enum": ["screenshot", "console_log", "dom_snapshot"]},
                    "evidence_content": {"type": "string", "description": "Captured evidence text, log, or file path"},
                },
                "required": ["summary", "evidence_type", "evidence_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Conclude exploration when testing is complete.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string", "description": "Final summary of test findings"}},
                "required": ["summary"],
            },
        },
    },
]


class BaselineAgent:
    """Explores a target web application black-box to detect and record software defects."""

    def __init__(
        self,
        llm_client: LLMClient,
        gateway: ToolGateway,
        run_state: Optional[RunState] = None,
        loop_detector: Optional[LoopDetector] = None,
        trace_writer: Optional[TraceWriter] = None,
        verdict_engine: Optional[VerdictEngine] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        self.client = llm_client
        self.gateway = gateway
        self.run_state = run_state or RunState()
        self.loop_detector = loop_detector or LoopDetector(threshold=3)
        self.trace_writer = trace_writer
        self.verdict_engine = verdict_engine or VerdictEngine()
        self.tools = tools if tools is not None else DEFAULT_TOOLS
        self._loop_recovery_triggered = False

    def run(self, objective: str, target: str, max_turns: int = 25) -> RunResult:
        system_prompt = (
            "You are an autonomous web QA testing agent. Your mission is to explore the target "
            "application, detect bugs, functional defects, console errors, or layout issues, "
            "and report verified findings with evidence. Always report findings before concluding."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Objective: {objective}\nTarget URL: {target}"},
        ]

        current_url = target
        last_obs = ""
        budget_exceeded = False

        if self.trace_writer:
            self.trace_writer.record({
                "type": "run_start",
                "objective": objective,
                "target": target,
                "model_id": getattr(self.client.provider, "model", "unknown"),
                "tokens": 0,
            })

        for _ in range(max_turns):
            try:
                self.run_state.check_budget()
            except BudgetExceeded:
                budget_exceeded = True
                break

            try:
                response = self.client.chat(messages, tools=self.tools)
            except Exception:
                break

            usage = response.get("usage", {})
            self.run_state.record_tokens(usage.get("total_tokens", 0))
            if self.trace_writer:
                self.trace_writer.record({
                    "type": "model_call",
                    "model_id": response.get("model", "unknown"),
                    "tokens": usage.get("total_tokens", 0),
                    "usage": usage,
                })

            choice = response.get("choices", [{}])[0]
            msg = choice.get("message", {})
            messages.append(msg)

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                break

            finished = False
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name")
                raw_args = func.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except Exception:
                        args = {}
                else:
                    args = raw_args

                if tool_name == "finish":
                    finished = True
                    break

                if tool_name == "report_finding":
                    ev_type_str = args.get("evidence_type", "dom_snapshot")
                    try:
                        ev_type = EvidenceType(ev_type_str)
                    except ValueError:
                        ev_type = EvidenceType.DOM_SNAPSHOT

                    ev = Evidence(
                        type=ev_type,
                        content=args.get("evidence_content", ""),
                        metadata={"url": current_url},
                    )
                    steps_list = [
                        {"fingerprint": fp} if isinstance(fp, str) else fp
                        for fp in self.run_state.history
                    ]
                    finding = Finding(
                        id=f"F-{len(self.run_state.findings) + 1}",
                        summary=args.get("summary", "Defect discovered"),
                        evidence=[ev],
                        steps=steps_list,
                    )
                    self.run_state.add_finding(finding)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", "tc-1"),
                        "name": tool_name,
                        "content": f"Finding recorded: {finding.id}",
                    })
                    continue

                # Browser/HTTP tools
                action_fp = compute_action_fingerprint(tool_name, args, current_url)
                obs_fp = compute_observation_fingerprint(last_obs)

                loop_action = self.loop_detector.check(action_fp, obs_fp)
                if loop_action in (RecoveryAction.RE_OBSERVE, RecoveryAction.TRY_ALTERNATE):
                    self._loop_recovery_triggered = True
                elif loop_action == RecoveryAction.TERMINATE_INCONCLUSIVE:
                    self._loop_recovery_triggered = True
                    finished = True
                    break

                try:
                    self.run_state.check_budget()
                    self.run_state.record_action(action_fp)
                except BudgetExceeded:
                    budget_exceeded = True
                    finished = True
                    break

                try:
                    res = self.gateway.execute(tool_name, args)
                    if isinstance(res, dict) and "url" in res:
                        current_url = res["url"]
                    if isinstance(res, dict) and "snapshot" in res:
                        last_obs = res["snapshot"]
                    res_str = json.dumps(res) if isinstance(res, (dict, list)) else str(res)
                except Exception as e:
                    res_str = f"Error executing {tool_name}: {e}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "tc-1"),
                    "name": tool_name,
                    "content": res_str,
                })

            if finished:
                break

        return RunResult(
            findings=self.run_state.findings,
            actions_count=self.run_state.actions_count,
            tokens_used=self.run_state.tokens_count,
            budget_exceeded=budget_exceeded,
            loop_recovery_triggered=self._loop_recovery_triggered,
            trace_path=str(self.trace_writer._path) if self.trace_writer else None,
        )
