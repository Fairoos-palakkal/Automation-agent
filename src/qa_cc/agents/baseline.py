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
from qa_cc.agents.loop import AgentLoop
from qa_cc.agents.step_log import StepLog
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
    is_mock: bool = False
    status: str = "completed"
    step_log: Optional[StepLog] = None


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
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_finding",
            "description": "Record a discovered software bug, visual error, broken link, or unexpected state with structured claims and evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Summary of the defect"},
                    "expected": {"type": "string", "description": "Expected behavior or UI/API state"},
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
        step_log: Optional[StepLog] = None,
        target_profile: Optional[Any] = None,
    ):
        self.client = llm_client
        self.gateway = gateway
        self.run_state = run_state if run_state is not None else RunState()
        self.step_log = step_log if step_log is not None else StepLog()
        self.loop_detector = loop_detector if loop_detector is not None else LoopDetector(threshold=3)
        self.trace_writer = trace_writer
        self.verdict_engine = verdict_engine if verdict_engine is not None else VerdictEngine()
        self.tools = tools if tools is not None else DEFAULT_TOOLS
        self.target_profile = target_profile
        self._loop_recovery_triggered = False

    def run(self, objective: str, target: str, max_turns: int = 25) -> RunResult:
        system_prompt = (
            "You are an autonomous web QA testing agent. Your mission is to explore the target "
            "application, detect bugs, functional defects, console errors, or layout issues, "
            "and report verified findings with evidence. Always report findings before concluding.\n\n"
            "Guidelines:\n"
            "- Interact with the application like a user: click buttons, click navigation links, and fill forms.\n"
            "- Do not navigate directly to static code assets (.js, .css). Explore through HTML pages and UI controls.\n"
            "- If an overlay, modal dialog, or banner covers interactive elements, dismiss it so page controls become accessible.\n"
            "- If a feature mentioned in the objective is absent, thoroughly test all available navigation paths and controls.\n"
            "- Whenever you observe unexpected behavior (unhandled exceptions, HTTP errors, broken form submission, or state inconsistencies), immediately call report_finding with evidence before concluding."
        )

        extra_content = None
        if self.target_profile and hasattr(self.target_profile, "format_for_prompt"):
            profile_hint = self.target_profile.format_for_prompt()
            if profile_hint:
                extra_content = f"Target Profile Context:\n{profile_hint}"

        loop = AgentLoop(
            client=self.client,
            gateway=self.gateway,
            tools=self.tools,
            system_prompt=system_prompt,
            run_state=self.run_state,
            step_log=self.step_log,
            trace_writer=self.trace_writer,
            loop_detector=self.loop_detector,
            verdict_engine=self.verdict_engine,
            agent_name="baseline",
            target_profile=self.target_profile,
        )
        loop_result = loop.run(
            objective=objective,
            target=target,
            max_turns=max_turns,
            extra_user_content=extra_content,
        )
        self._loop_recovery_triggered = loop_result.loop_recovery_triggered
        return loop_result.to_run_result()

