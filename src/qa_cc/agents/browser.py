"""BrowserAgent — Isolated sub-agent executing browser automation tasks (Phase 2.3).

Responsibilities:
- Executes Tasks assigned by the Planner using browser tools only.
- Completely isolated context: receives only its assigned Task, not full orchestrator history.
- Enforces per-task budget (actions, tokens) via its own RunState.
- Returns TaskResult containing Findings and recorded steps, NOT raw LLM transcripts (D6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Dict, List, Optional

from qa_cc.agents.loop_detector import (
    LoopDetector,
    RecoveryAction,
    compute_action_fingerprint,
    compute_observation_fingerprint,
)
from qa_cc.agents.plan import Task
from qa_cc.gateway.gateway import ToolGateway
from qa_cc.llm.client import LLMClient
from qa_cc.trace.run_state import RunState, BudgetExceeded
from qa_cc.trace.writer import TraceWriter
from qa_cc.verdict.evidence import Evidence, EvidenceType, Finding


@dataclass
class TaskResult:
    task_id: str
    status: str = "completed"
    findings: List[Finding] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    actions_count: int = 0
    tokens_used: int = 0
    budget_exceeded: bool = False
    loop_recovery_triggered: bool = False


BROWSER_TOOLS: List[Dict[str, Any]] = [
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
            "description": "Record a discovered defect with evidence.",
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


class BrowserAgent:
    """Carries out browser automation Tasks in isolation."""

    def __init__(
        self,
        llm_client: LLMClient,
        gateway: ToolGateway,
        trace_writer: Optional[TraceWriter] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        loop_detector: Optional[LoopDetector] = None,
    ):
        self.client = llm_client
        self.gateway = gateway
        self.trace_writer = trace_writer
        self.tools = tools if tools is not None else BROWSER_TOOLS
        self.loop_detector = loop_detector or LoopDetector(threshold=3)

    def execute(self, task: Task, target_url: str = "", max_turns: int = 25) -> TaskResult:
        """Execute a browser task under its own dedicated budget and context."""
        max_actions = task.budget.get("max_actions", 25)
        max_tokens = task.budget.get("max_tokens", 100_000)
        run_state = RunState(max_actions=max_actions, max_tokens=max_tokens)

        system_prompt = (
            "You are an isolated Browser QA Agent. Your mission is to accomplish the assigned Task goal "
            "using browser automation tools (navigate, click, fill, screenshot).\n\n"
            "Guidelines for Testing & Defect Detection:\n"
            "1. Modal & Overlay Dismissal: On modern Single Page Apps (SPAs), dismiss any welcome dialogs, "
            "cookie banners, or overlays first so that page elements become interactive. Look for selectors like "
            "'button[aria-label=\"Close Welcome Banner\"]', '.close-dialog', 'button.mat-mdc-button', or '.cc-btn.cc-dismiss'.\n"
            "2. Interactive Exploration: Explore like a user and a security tester. Identify input fields (#email, #password, "
            "#searchQuery, input[name='q'], etc.) and submit buttons (#loginButton, button[type='submit']).\n"
            "3. Boundary & Security Probing: Test inputs with boundary values, special characters, and SQL injection strings "
            "(e.g. \"' or 1=1--\" in login forms, or \"'--\" and \"<script>\" in search forms). Check whether invalid inputs bypass "
            "authentication, return raw SQL/stack traces, or trigger 500 errors.\n"
            "4. Reporting Findings: Whenever you observe a bug (authentication bypass, unhandled error, console crash, broken state, "
            "or data leak), IMMEDIATELY call report_finding with evidence (dom_snapshot or screenshot) and a descriptive summary.\n"
            "5. Stay strictly within the scope of your assigned task, and call finish when done."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task ID: {task.id}\nGoal: {task.goal}\nTarget URL: {target_url}"},
        ]

        current_url = target_url
        last_obs = ""
        budget_exceeded = False
        loop_recovery_triggered = False
        summary = ""
        recorded_steps: List[Dict[str, Any]] = []

        for _ in range(max_turns):
            try:
                run_state.check_budget()
            except BudgetExceeded:
                budget_exceeded = True
                break

            try:
                response = self.client.chat(messages, tools=self.tools)
            except Exception:
                break

            usage = response.get("usage", {})
            run_state.record_tokens(usage.get("total_tokens", 0))

            if self.trace_writer:
                self.trace_writer.record({
                    "type": "subagent_model_call",
                    "task_id": task.id,
                    "agent": "browser",
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
                    summary = args.get("summary", "Task concluded")
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
                        metadata={"url": current_url, "task_id": task.id},
                    )
                    finding = Finding(
                        id=f"F-{task.id}-{len(run_state.findings) + 1}",
                        summary=args.get("summary", "Defect discovered"),
                        evidence=[ev],
                        steps=list(recorded_steps),
                        metadata={"task_id": task.id, "assignee": "browser"},
                    )
                    run_state.add_finding(finding)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", "tc-1"),
                        "name": tool_name,
                        "content": f"Finding recorded: {finding.id}",
                    })
                    continue

                # Browser actions
                action_fp = compute_action_fingerprint(tool_name, args, current_url)
                obs_fp = compute_observation_fingerprint(last_obs)

                loop_action = self.loop_detector.check(action_fp, obs_fp)
                if loop_action in (RecoveryAction.RE_OBSERVE, RecoveryAction.TRY_ALTERNATE):
                    loop_recovery_triggered = True
                elif loop_action == RecoveryAction.TERMINATE_INCONCLUSIVE:
                    loop_recovery_triggered = True
                    finished = True
                    break

                try:
                    run_state.check_budget()
                    run_state.record_action(action_fp)
                except BudgetExceeded:
                    budget_exceeded = True
                    finished = True
                    break

                step_record = {
                    "tool": tool_name,
                    "args": args,
                    "fingerprint": action_fp,
                }
                recorded_steps.append(step_record)

                try:
                    res = self.gateway.execute(tool_name, args)
                    if isinstance(res, dict) and "url" in res:
                        current_url = res["url"]
                    if isinstance(res, dict) and "snapshot" in res:
                        last_obs = res["snapshot"]
                    res_str = json.dumps(res, default=str) if isinstance(res, (dict, list)) else str(res)
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

        status = "budget_exceeded" if budget_exceeded else "completed"

        return TaskResult(
            task_id=task.id,
            status=status,
            findings=run_state.findings,
            steps=recorded_steps,
            summary=summary,
            actions_count=run_state.actions_count,
            tokens_used=run_state.tokens_count,
            budget_exceeded=budget_exceeded,
            loop_recovery_triggered=loop_recovery_triggered,
        )
