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
from qa_cc.security.fence import SECURITY_INSTRUCTION


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
    step_log: Optional[StepLog] = None


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
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_finding",
            "description": "Record a discovered defect with structured claims, observations, and evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Summary of the defect"},
                    "expected": {"type": "string", "description": "Expected behavior or UI state"},
                    "actual": {"type": "string", "description": "Actual observed defect behavior"},
                    "selector_or_url": {"type": "string", "description": "CSS selector or URL where defect occurred"},
                    "step_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of steps in StepLog that reproduce defect (e.g. ['step-1', 'step-2'])",
                    },
                    "evidence_type": {"type": "string", "enum": ["screenshot", "console_log", "dom_snapshot", "network_request"]},
                    "evidence_content": {"type": "string", "description": "Optional evidence text or path (runtime automatically captures real observation)"},
                },
                "required": ["summary"],
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
    {
        "type": "function",
        "function": {
            "name": "console_errors",
            "description": "Inspect uncaught page JavaScript errors and browser console error logs.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


from qa_cc.agents.loop import AgentLoop
from qa_cc.agents.step_log import StepLog


class BrowserAgent:
    """Carries out browser automation Tasks in isolation."""

    def __init__(
        self,
        llm_client: LLMClient,
        gateway: ToolGateway,
        trace_writer: Optional[TraceWriter] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        loop_detector: Optional[LoopDetector] = None,
        step_log: Optional[StepLog] = None,
    ):
        self.client = llm_client
        self.gateway = gateway
        self.trace_writer = trace_writer
        self.tools = tools if tools is not None else BROWSER_TOOLS
        self.loop_detector = loop_detector or LoopDetector(threshold=3)
        self.step_log = step_log

    def new_context(self) -> None:
        """Reset browser context for isolation across tasks."""
        driver = getattr(self.gateway, "driver", None)
        if driver and hasattr(driver, "new_context"):
            driver.new_context()

    def execute(
        self,
        task: Task,
        target_url: str = "",
        max_turns: int = 25,
        step_log: Optional[StepLog] = None,
    ) -> TaskResult:
        """Execute a browser task under its own dedicated budget and context."""
        self.new_context()
        max_actions = task.budget.get("max_actions", 25)
        max_tokens = task.budget.get("max_tokens", 100_000)
        run_state = RunState(max_actions=max_actions, max_tokens=max_tokens)
        active_step_log = step_log or self.step_log or StepLog()

        system_prompt = (
            "You are an isolated Browser QA Agent. Your mission is to accomplish the assigned Task goal "
            "using browser automation tools (navigate, click, fill, screenshot).\n\n"
            "Guidelines for Testing & Defect Detection:\n"
            "1. Modal & Overlay Dismissal: Dismiss any welcome dialogs, cookie banners, or overlays first "
            "so that page elements become interactive.\n"
            "2. Interactive Exploration: Explore form fields and action controls methodically. Identify input fields "
            "and submit buttons across the page.\n"
            "3. Boundary & Error Probing: Test inputs with boundary values, special characters, and unexpected formats. "
            "Observe whether invalid inputs trigger unhandled exceptions, raw database errors, stack traces, or 500 status codes.\n"
            "4. Reporting Findings: Whenever you observe a defect (unhandled error, console crash, broken state, "
            "or data leak), IMMEDIATELY call report_finding with evidence (dom_snapshot or screenshot) and a descriptive summary.\n"
            "5. Stay strictly within the scope of your assigned task, and call finish when done.\n\n"
            f"{SECURITY_INSTRUCTION}"
        )

        prior_findings = task.metadata.get("prior_findings", [])
        findings_section = ""
        if prior_findings:
            rendered = "\n".join(f"- {f.get('id', 'F')}: {f.get('summary', '')}" for f in prior_findings)
            findings_section = f"\n\nPreviously Discovered Findings (do not duplicate):\n{rendered}"

        user_content = f"Task ID: {task.id}\nGoal: {task.goal}\nTarget URL: {target_url}{findings_section}"
        loop = AgentLoop(
            client=self.client,
            gateway=self.gateway,
            tools=self.tools,
            system_prompt=system_prompt,
            run_state=run_state,
            step_log=active_step_log,
            trace_writer=self.trace_writer,
            loop_detector=self.loop_detector,
            agent_name="browser",
            task_id=task.id,
        )
        loop_result = loop.run(
            target=target_url,
            max_turns=max_turns,
            extra_user_content=user_content,
        )
        return loop_result.to_task_result(task_id=task.id)


