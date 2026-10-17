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
            "You are an expert QA Test Planner. Your responsibility is to analyze the testing objective "
            "and target metadata, then decompose the objective into complementary, high-impact Tasks.\n"
            "Guidelines:\n"
            "- Balance tasks between 'browser' (for UI navigation, dismissing modals, form submissions) "
            "and 'api' (for probing REST endpoints for unhandled server errors, 500 status codes, or validation flaws).\n"
            "- Formulate concrete goals for each task so the agent knows what functional areas to probe.\n"
            "- Allocate generous action budgets (e.g. 15 to 25 actions per task) to allow thorough probing and verification.\n"
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

    def _parse_plan(self, resp: dict) -> Plan:
        """Parse LLM response into Plan, stripping fences and handling empty responses."""
        content = resp.get("choices", [{}])[0].get("message", {}).get("content")
        if not content:
            raise ValueError("Response content is empty or None")
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if len(lines) >= 2 and lines[-1].strip() == "```":
                content = "\n".join(lines[1:-1]).strip()
            elif content.startswith("```json"):
                content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
        data = json.loads(content)
        return Plan(**data)

    def plan(
        self,
        objective: str,
        target_metadata: Optional[Dict[str, Any]] = None,
        total_budget: Optional[Dict[str, int]] = None,
    ) -> Plan:
        """Create an initial Plan from an Objective and target metadata."""
        system_prompt = (
            "You are an expert QA Test Planner. Your responsibility is to analyze the testing objective "
            "and target metadata, then decompose the objective into complementary, high-impact Tasks.\n"
            "Guidelines:\n"
            "- Balance tasks between 'browser' (for UI navigation, dismissing modals, form submissions) "
            "and 'api' (for probing REST endpoints for unhandled server errors, 500 status codes, or validation flaws).\n"
            "- Formulate concrete goals for each task so the agent knows what functional areas to probe.\n"
            "- Allocate generous action budgets (e.g. 15 to 25 actions per task) to allow thorough probing and verification.\n"
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

        plan = self.client.chat_with_schema(messages, parse_fn=self._parse_plan)

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

        plan = self.client.chat_with_schema(messages, parse_fn=self._parse_plan)

        if total_budget:
            self._enforce_budget_split(plan, total_budget)

        return plan

    def _enforce_budget_split(self, plan: Plan, total_budget: Dict[str, int]) -> None:
        """Ensure the sum of task budgets does not exceed total_budget using integer division with remainder."""
        if not plan.tasks:
            return

        max_actions = total_budget.get("max_actions")
        if max_actions is not None:
            sum_actions = sum(t.budget.get("max_actions", 0) for t in plan.tasks)
            if sum_actions > max_actions:
                if max_actions <= 0:
                    for t in plan.tasks:
                        t.budget["max_actions"] = 0
                elif sum_actions > 0:
                    raw_shares = [
                        (t.budget.get("max_actions", 0) * max_actions) / sum_actions
                        for t in plan.tasks
                    ]
                    base_alloc = [int(s) for s in raw_shares]
                    remainder = max_actions - sum(base_alloc)
                    fractions = [
                        (raw_shares[i] - base_alloc[i], i)
                        for i in range(len(plan.tasks))
                    ]
                    fractions.sort(reverse=True, key=lambda x: x[0])
                    for k in range(remainder):
                        idx = fractions[k][1]
                        base_alloc[idx] += 1
                    for i, t in enumerate(plan.tasks):
                        t.budget["max_actions"] = base_alloc[i]

        max_tokens = total_budget.get("max_tokens")
        if max_tokens is not None:
            sum_tokens = sum(t.budget.get("max_tokens", 0) for t in plan.tasks)
            if sum_tokens > max_tokens:
                if max_tokens <= 0:
                    for t in plan.tasks:
                        t.budget["max_tokens"] = 0
                elif sum_tokens > 0:
                    raw_shares = [
                        (t.budget.get("max_tokens", 0) * max_tokens) / sum_tokens
                        for t in plan.tasks
                    ]
                    base_alloc = [int(s) for s in raw_shares]
                    remainder = max_tokens - sum(base_alloc)
                    fractions = [
                        (raw_shares[i] - base_alloc[i], i)
                        for i in range(len(plan.tasks))
                    ]
                    fractions.sort(reverse=True, key=lambda x: x[0])
                    for k in range(remainder):
                        idx = fractions[k][1]
                        base_alloc[idx] += 1
                    for i, t in enumerate(plan.tasks):
                        t.budget["max_tokens"] = base_alloc[i]
