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
            "description": "Record a discovered API defect with structured claims, observations, and evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Summary of the defect"},
                    "expected": {"type": "string", "description": "Expected status code or response structure"},
                    "actual": {"type": "string", "description": "Actual observed response status or body error"},
                    "selector_or_url": {"type": "string", "description": "API URL/endpoint where defect occurred"},
                    "step_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of steps in StepLog that reproduce defect (e.g. ['step-1', 'step-2'])",
                    },
                    "evidence_type": {"type": "string", "enum": ["network_request", "dom_snapshot", "console_log"]},
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
            "description": "Conclude API testing when work is complete.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string", "description": "Final summary of test findings"}},
                "required": ["summary"],
            },
        },
    },
]
from qa_cc.agents.loop import AgentLoop
from qa_cc.agents.step_log import StepLog


class APIAgent:
    """Carries out HTTP / REST API testing Tasks in isolation."""

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
        step_log = StepLog()

        system_prompt = (
            "You are an isolated API QA Agent. Your mission is to accomplish the assigned Task goal "
            "using the http_request tool. Test endpoints for bugs, validation issues, security flaws, or server errors.\n\n"
            "Guidelines for API Testing & Defect Detection:\n"
            "1. Endpoint Discovery: Web SPAs communicate with REST APIs under '/rest/...' and '/api/...'. "
            "Probe key functional endpoints relevant to your task:\n"
            "   - Authentication: POST /rest/user/login (with JSON body), /api/Users, /rest/user/whoami\n"
            "   - Search & Data: GET /rest/products/search?q=... , /api/Products, /api/Challenges\n"
            "   - User State: /rest/basket/..., /api/BasketItems, /rest/saveLoginIp\n"
            "2. Injection & Robustness Probing:\n"
            "   - SQL Injection in Login: Test POST /rest/user/login with {\"email\": \"' or 1=1--\", \"password\": \"x\"}. "
            "If it returns HTTP 200 with an auth token, report this critical SQL injection / auth bypass immediately!\n"
            "   - Search Query Vulnerabilities: Test GET /rest/products/search?q=apple'-- or q=' union select ... . "
            "If it returns HTTP 500, leaks internal database errors ('SQLITE_ERROR', stack trace), report it immediately!\n"
            "   - Boundary & Error Conditions: Send empty bodies, invalid types, or malformed JSON to endpoints and verify "
            "if the server responds with clean 4xx errors or unhandled 500 crashes.\n"
            "3. Immediate Reporting: Whenever you detect an unexpected 200 (auth bypass), 500 Internal Server Error, "
            "SQL error leak, or missing authorization, IMMEDIATELY call report_finding with evidence_type='network_request' "
            "and evidence_content containing the request method, URL, status code, and response body before finishing.\n"
            "4. Stay strictly within the scope of your assigned task, and call finish when done."
        )

        user_content = f"Task ID: {task.id}\nGoal: {task.goal}\nBase URL: {base_url}"
        loop = AgentLoop(
            client=self.client,
            gateway=self.gateway,
            tools=self.tools,
            system_prompt=system_prompt,
            run_state=run_state,
            step_log=step_log,
            trace_writer=self.trace_writer,
            loop_detector=self.loop_detector,
            agent_name="api",
            task_id=task.id,
        )
        loop_result = loop.run(
            target=base_url,
            max_turns=max_turns,
            extra_user_content=user_content,
        )
        return loop_result.to_task_result(task_id=task.id)
