"""Tests for Plan and Task Pydantic models — Phase 2.1 (Red → Green)."""
import pytest
from pydantic import ValidationError

from qa_cc.agents.plan import Plan, Task, AgentType


class TestPlanSchema:
    def test_plan_validates_against_schema(self):
        """A well-formed Plan dict validates successfully."""
        plan_data = {
            "objective": "Test the checkout flow",
            "tasks": [
                {
                    "id": "task-1",
                    "goal": "Explore the checkout page for UI defects",
                    "assignee": "browser",
                    "budget": {"max_actions": 10, "max_tokens": 10000},
                },
                {
                    "id": "task-2",
                    "goal": "Test the API endpoints for validation issues",
                    "assignee": "api",
                    "budget": {"max_actions": 5, "max_tokens": 5000},
                },
            ],
        }
        plan = Plan(**plan_data)
        assert plan.objective == "Test the checkout flow"
        assert len(plan.tasks) == 2
        assert plan.tasks[0].assignee == AgentType.BROWSER
        assert plan.tasks[1].assignee == AgentType.API

    def test_plan_rejects_missing_assignee(self):
        """Task without assignee raises ValidationError."""
        with pytest.raises(ValidationError):
            Task(
                id="task-1",
                goal="Explore the checkout page",
                budget={"max_actions": 10, "max_tokens": 5000},
            )

    def test_plan_rejects_unknown_assignee(self):
        """Task with assignee='unknown' raises ValidationError."""
        with pytest.raises(ValidationError):
            Task(
                id="task-1",
                goal="Explore the checkout page",
                assignee="unknown",
                budget={"max_actions": 10, "max_tokens": 5000},
            )

    def test_plan_tasks_have_budgets(self):
        """Each Task in a Plan has a budget field."""
        task = Task(
            id="task-1",
            goal="Explore the checkout page",
            assignee="browser",
            budget={"max_actions": 10, "max_tokens": 5000},
        )
        assert task.budget is not None
        assert task.budget["max_actions"] == 10
        assert task.budget["max_tokens"] == 5000

    def test_plan_serializes_for_trace(self):
        """Plan serializes to a dict suitable for trace recording."""
        plan = Plan(
            objective="Test checkout",
            tasks=[
                Task(
                    id="task-1",
                    goal="Test UI",
                    assignee="browser",
                    budget={"max_actions": 10, "max_tokens": 5000},
                )
            ],
        )
        data = plan.model_dump()
        assert isinstance(data, dict)
        assert "objective" in data
        assert "tasks" in data
        assert isinstance(data["tasks"], list)
        assert data["tasks"][0]["assignee"] == "browser"
