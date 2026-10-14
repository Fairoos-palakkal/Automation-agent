"""Planner Agent — Phase 2.2.

The Planner Agent turns an Objective and Target metadata into a structured Plan
consisting of Tasks assigned to BrowserAgent or APIAgent.

Key invariants:
- Has NO direct tool access (tools list is empty).
- Produces a validated Plan model with per-task budgets.
- Supports bounded replanning upon receiving sub-agent reports (max 2 replans).
- Ensures task budgets do not exceed total run budget.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from qa_cc.agents.plan import Plan, Task
from qa_cc.llm.client import LLMClient


class ReplanLimitExceeded(Exception):
    """Raised when the maximum number of replan attempts is exceeded."""


class Planner:
    """Agent that creates and revises testing Plans."""

    def __init__(
        self,
        llm_client: LLMClient,
        max_replans: int = 2,
    ):
        self.client = llm_client
        self.max_replans = max_replans
        self.tools: List[Any] = []
        self._replan_count = 0

    def plan(
        self,
        objective: str,
        target_metadata: Optional[Dict[str, Any]] = None,
        total_budget: Optional[Dict[str, int]] = None,
    ) -> Plan:
        """Create an initial Plan from an Objective and target metadata."""
        system_prompt = (
            "You are a QA Test Planner. Your responsibility is to analyze the testing objective "
            "and target metadata, then decompose the objective into specific Tasks. "
            "Assign each task to either 'browser' (for UI/navigation testing) or 'api' (for HTTP/REST testing). "
            "Respond ONLY with valid JSON matching the Plan schema:\n"
            "{\n"
            '  "objective": "...",\n'
            '  "tasks": [\n'
            '    {"id": "task-1", "goal": "...", "assignee": "browser"|"api", "budget": {"max_actions": int, "max_tokens": int}}\n'
            "  ]\n"
            "}"
        )

        user_content = f"Objective: {objective}\nTarget Metadata: {json.dumps(target_metadata or {})}"
        if total_budget:
            user_content += f"\nTotal Budget Constraints: {json.dumps(total_budget)}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        def _parse(resp: dict) -> Plan:
            content = resp["choices"][0]["message"]["content"]
            data = json.loads(content)
            return Plan(**data)

        plan = self.client.chat_with_schema(messages, parse_fn=_parse)

        if total_budget:
            self._enforce_budget_split(plan, total_budget)

        return plan

    def replan(
        self,
        original_plan: Plan,
        agent_report: str,
        total_budget: Optional[Dict[str, int]] = None,
    ) -> Plan:
        """Revise a Plan based on feedback/results from a sub-agent."""
        if self._replan_count >= self.max_replans:
            raise ReplanLimitExceeded(
                f"Maximum replan limit reached ({self.max_replans}). Further replans are rejected."
            )

        self._replan_count += 1

        system_prompt = (
            "You are a QA Test Planner. A sub-agent has executed a task and returned a report. "
            "Revise the remaining Tasks or create new Tasks to pursue the objective based on this feedback. "
            "Respond ONLY with valid JSON matching the Plan schema."
        )

        user_content = (
            f"Original Plan: {json.dumps(original_plan.model_dump())}\n"
            f"Sub-agent Report: {agent_report}"
        )
        if total_budget:
            user_content += f"\nRemaining Budget Constraints: {json.dumps(total_budget)}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        def _parse(resp: dict) -> Plan:
            content = resp["choices"][0]["message"]["content"]
            data = json.loads(content)
            return Plan(**data)

        plan = self.client.chat_with_schema(messages, parse_fn=_parse)

        if total_budget:
            self._enforce_budget_split(plan, total_budget)

        return plan

    def _enforce_budget_split(self, plan: Plan, total_budget: Dict[str, int]) -> None:
        """Ensure the sum of task budgets does not exceed total_budget."""
        max_actions = total_budget.get("max_actions")
        max_tokens = total_budget.get("max_tokens")

        if not plan.tasks:
            return

        if max_actions is not None:
            sum_actions = sum(t.budget.get("max_actions", 0) for t in plan.tasks)
            if sum_actions > max_actions and sum_actions > 0:
                scale = max_actions / sum_actions
                for t in plan.tasks:
                    t.budget["max_actions"] = max(1, int(t.budget.get("max_actions", 0) * scale))

        if max_tokens is not None:
            sum_tokens = sum(t.budget.get("max_tokens", 0) for t in plan.tasks)
            if sum_tokens > max_tokens and sum_tokens > 0:
                scale = max_tokens / sum_tokens
                for t in plan.tasks:
                    t.budget["max_tokens"] = max(1, int(t.budget.get("max_tokens", 0) * scale))
