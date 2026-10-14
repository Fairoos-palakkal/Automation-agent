"""APIAgent — Isolated sub-agent executing HTTP/REST API tasks (Phase 2.4).

Responsibilities:
- Executes Tasks assigned by the Planner using HTTP tools only.
- Completely isolated context: receives only its assigned Task, not full orchestrator history.
- Enforces per-task budget (actions, tokens) via its own RunState.
- Returns TaskResult containing Findings and recorded steps, NOT raw LLM transcripts (D6).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from qa_cc.agents.browser import TaskResult
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


API_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "http_request",
            "description": "Send an HTTP request (GET, POST, PUT, DELETE, etc.) to an API endpoint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "description": "HTTP method like GET, POST, PUT, DELETE"},
                    "url": {"type": "string", "description": "Target API URL"},
                    "headers": {"type": "object", "description": "Optional HTTP headers"},
                    "body": {"type": "string", "description": "Optional request body (string or JSON)"},
                },
                "required": ["method", "url"],
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
                    "evidence_type": {"type": "string", "enum": ["network_request", "dom_snapshot", "console_log"]},
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
            "description": "Conclude API testing when work is complete.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string", "description": "Final summary of test findings"}},
                "required": ["summary"],
            },
        },
    },
]


class APIAgent:
    """Carries out HTTP/REST testing Tasks in isolation."""

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
        self.tools = tools if tools is not None else API_TOOLS
        self.loop_detector = loop_detector or LoopDetector(threshold=3)

    def execute(self, task: Task, base_url: str = "", max_turns: int = 25) -> TaskResult:
        """Execute an API task under its own dedicated budget and context."""
        max_actions = task.budget.get("max_actions", 25)
        max_tokens = task.budget.get("max_tokens", 100_000)
        run_state = RunState(max_actions=max_actions, max_tokens=max_tokens)

        system_prompt = (
            "You are an isolated API QA Agent. Your mission is to accomplish the assigned Task goal "
            "using the http_request tool. Test endpoints for bugs, validation issues, or server errors. "
            "Detect defects, report findings with evidence, and conclude with finish. "
            "Stay strictly within the scope of your assigned task."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task ID: {task.id}\nGoal: {task.goal}\nBase URL: {base_url}"},
        ]

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
                    "agent": "api",
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
                    ev_type_str = args.get("evidence_type", "network_request")
                    try:
                        ev_type = EvidenceType(ev_type_str)
                    except ValueError:
                        ev_type = EvidenceType.NETWORK_REQUEST

                    ev = Evidence(
                        type=ev_type,
                        content=args.get("evidence_content", ""),
                        metadata={"task_id": task.id, "base_url": base_url},
                    )
                    finding = Finding(
                        id=f"F-{task.id}-{len(run_state.findings) + 1}",
                        summary=args.get("summary", "API Defect discovered"),
                        evidence=[ev],
                        steps=list(recorded_steps),
                        metadata={"task_id": task.id, "assignee": "api"},
                    )
                    run_state.add_finding(finding)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", "tc-api-1"),
                        "name": tool_name,
                        "content": f"Finding recorded: {finding.id}",
                    })
                    continue

                # HTTP actions
                target_url = args.get("url", base_url)
                action_fp = compute_action_fingerprint(tool_name, args, target_url)
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
                    if isinstance(res, dict) and "body" in res:
                        last_obs = str(res["body"])
                    res_str = json.dumps(res, default=str) if isinstance(res, (dict, list)) else str(res)
                except Exception as e:
                    res_str = f"Error executing {tool_name}: {e}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "tc-api-1"),
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
