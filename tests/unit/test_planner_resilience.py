"""Tests for Planner resilience, fenced JSON, validation, and integer budget split — Ticket T-22 (F-21)."""
import json
import pytest
from pydantic import ValidationError

from qa_cc.agents.plan import AgentType, Plan, Task, TaskBudget
from qa_cc.agents.planner import Planner
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider


def make_plan_content(content_str: str):
    return {
        "id": "call-plan",
        "model": "fake-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content_str,
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


class TestPlannerResilience:
    def test_planner_accepts_fenced_json(self):
        """Planner strips markdown json fences and parses successfully."""
        plan_dict = {
            "objective": "Test checkout",
            "tasks": [
                {
                    "id": "task-1",
                    "goal": "Verify UI form",
                    "assignee": "browser",
                    "budget": {"max_actions": 10, "max_tokens": 5000},
                }
            ],
        }
        fenced_json = f"```json\n{json.dumps(plan_dict, indent=2)}\n```"

        provider = FakeProvider(responses=[make_plan_content(fenced_json)])
        client = LLMClient(provider=provider)
        planner = Planner(llm_client=client)

        plan = planner.plan(objective="Test checkout")
        assert len(plan.tasks) == 1
        assert plan.tasks[0].id == "task-1"
        assert plan.tasks[0].budget.max_actions == 10

    def test_planner_rejects_empty_plan(self):
        """Plan with zero tasks raises ValidationError."""
        with pytest.raises(ValidationError, match="at least 1 task"):
            Plan(objective="Test", tasks=[])

    def test_planner_rejects_duplicate_task_ids(self):
        """Plan with duplicate task IDs raises ValidationError."""
        t1 = Task(id="task-dup", goal="Goal 1", assignee=AgentType.BROWSER)
        t2 = Task(id="task-dup", goal="Goal 2", assignee=AgentType.API)
        with pytest.raises(ValidationError, match="unique"):
            Plan(objective="Test", tasks=[t1, t2])

    def test_planner_rejects_more_than_six_tasks(self):
        """Plan with more than 6 tasks raises ValidationError."""
        tasks = [
            Task(id=f"task-{i}", goal=f"Goal {i}", assignee=AgentType.BROWSER)
            for i in range(7)
        ]
        with pytest.raises(ValidationError, match="more than 6"):
            Plan(objective="Test", tasks=tasks)

    def test_typed_budget_validates_positive_integers(self):
        """TaskBudget requires non-negative integers."""
        budget = TaskBudget(max_actions=15, max_tokens=10000)
        assert budget.max_actions == 15
        assert budget["max_actions"] == 15
        assert budget.get("max_tokens") == 10000

        with pytest.raises(ValidationError):
            TaskBudget(max_actions=-1)

    def test_planner_retries_with_error_appended(self):
        """When provider returns malformed output, LLMClient appends the error message on retry."""
        valid_plan = {
            "objective": "Test checkout",
            "tasks": [{"id": "task-1", "goal": "Verify UI", "assignee": "browser"}],
        }
        # Attempt 1: malformed invalid json
        # Attempt 2: valid json
        provider = FakeProvider(responses=[
            make_plan_content("INVALID_NOT_JSON"),
            make_plan_content(json.dumps(valid_plan)),
        ])
        client = LLMClient(provider=provider)
        planner = Planner(llm_client=client)

        plan = planner.plan(objective="Test checkout")
        assert len(plan.tasks) == 1

        # Check that provider received the error feedback in the second call
        second_call_messages = provider.calls[1]["messages"]
        assert any("could not be parsed" in m.get("content", "") for m in second_call_messages)

    def test_integer_budget_split_sum_at_most_total(self):
        """Integer budget split guarantees sum(task.budget) <= total_budget even with small totals."""
        tasks = [
            Task(id=f"task-{i}", goal=f"Goal {i}", assignee=AgentType.BROWSER, budget=TaskBudget(max_actions=20, max_tokens=50000))
            for i in range(5)
        ]
        plan = Plan(objective="Test", tasks=tasks)

        provider = FakeProvider(responses=[])
        client = LLMClient(provider=provider)
        planner = Planner(llm_client=client)

        # 5 tasks with total budget of 3 actions:
        # Previously clamped each to 1 giving sum=5 > 3!
        # Now integer split with remainder gives sum <= 3
        planner._enforce_budget_split(plan, {"max_actions": 3, "max_tokens": 10000})

        sum_actions = sum(t.budget.max_actions for t in plan.tasks)
        sum_tokens = sum(t.budget.max_tokens for t in plan.tasks)

        assert sum_actions <= 3
        assert sum_tokens <= 10000
        # Check non-negative
        for t in plan.tasks:
            assert t.budget.max_actions >= 0
            assert t.budget.max_tokens >= 0

    def test_budget_split_with_exact_allocation(self):
        """Integer budget split distributes remainder by largest fraction."""
        # 3 tasks with initial budgets 10, 10, 10
        tasks = [
            Task(id="t1", goal="g1", assignee=AgentType.BROWSER, budget=TaskBudget(max_actions=10, max_tokens=1000)),
            Task(id="t2", goal="g2", assignee=AgentType.BROWSER, budget=TaskBudget(max_actions=10, max_tokens=1000)),
            Task(id="t3", goal="g3", assignee=AgentType.BROWSER, budget=TaskBudget(max_actions=10, max_tokens=1000)),
        ]
        plan = Plan(objective="Test", tasks=tasks)

        provider = FakeProvider(responses=[])
        client = LLMClient(provider=provider)
        planner = Planner(llm_client=client)

        planner._enforce_budget_split(plan, {"max_actions": 7, "max_tokens": 2500})

        sum_actions = sum(t.budget.max_actions for t in plan.tasks)
        sum_tokens = sum(t.budget.max_tokens for t in plan.tasks)

        assert sum_actions == 7
        assert sum_tokens == 2500
