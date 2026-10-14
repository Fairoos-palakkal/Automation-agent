"""Tests for Planner agent — Phase 2.2 (Red → Green)."""
import json
import pytest

from qa_cc.agents.plan import Plan, AgentType
from qa_cc.agents.planner import Planner
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider


def make_plan_response(plan_dict: dict):
    """Build a FakeProvider response that returns a Plan JSON as assistant content."""
    return {
        "id": "call-plan",
        "model": "fake-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(plan_dict),
                    "tool_calls": None,
                }
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 50, "total_tokens": 70},
    }


VALID_PLAN = {
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
            "goal": "Test the payment API endpoints",
            "assignee": "api",
            "budget": {"max_actions": 5, "max_tokens": 5000},
        },
    ],
}


class TestPlanner:
    def test_planner_returns_valid_plan(self):
        """Planner with FakeProvider returning Plan JSON returns a validated Plan."""
        provider = FakeProvider(responses=[make_plan_response(VALID_PLAN)])
        client = LLMClient(provider=provider)

        planner = Planner(llm_client=client)
        plan = planner.plan(
            objective="Test the checkout flow",
            target_metadata={"pages": ["/checkout.html"], "forms": ["payment-form"]},
        )

        assert isinstance(plan, Plan)
        assert plan.objective == "Test the checkout flow"
        assert len(plan.tasks) == 2
        assert plan.tasks[0].assignee == AgentType.BROWSER
        assert plan.tasks[1].assignee == AgentType.API

    def test_planner_has_no_tool_access(self):
        """Planner has an empty tool set — it must not have any tool access."""
        provider = FakeProvider(responses=[make_plan_response(VALID_PLAN)])
        client = LLMClient(provider=provider)

        planner = Planner(llm_client=client)
        assert planner.tools == [] or planner.tools is None

    def test_planner_replan_on_report(self):
        """Given a sub-agent report, Planner produces a revised Plan."""
        revised_plan = {
            "objective": "Test the checkout flow",
            "tasks": [
                {
                    "id": "task-1-revised",
                    "goal": "Focus on payment form validation",
                    "assignee": "browser",
                    "budget": {"max_actions": 8, "max_tokens": 8000},
                }
            ],
        }
        provider = FakeProvider(responses=[make_plan_response(revised_plan)])
        client = LLMClient(provider=provider)

        planner = Planner(llm_client=client)
        report = "BrowserAgent found no defects on checkout page. Recommend deeper form testing."
        plan = planner.replan(
            original_plan=Plan(**VALID_PLAN),
            agent_report=report,
        )

        assert isinstance(plan, Plan)
        assert len(plan.tasks) == 1
        assert plan.tasks[0].id == "task-1-revised"

    def test_planner_replan_bounded(self):
        """After max_replans reached, further replan calls raise an error."""
        # Planner with max_replans=2 should reject the 3rd replan attempt
        provider = FakeProvider(responses=[
            make_plan_response(VALID_PLAN),
            make_plan_response(VALID_PLAN),
        ])
        client = LLMClient(provider=provider)

        planner = Planner(llm_client=client, max_replans=2)

        # Two replans should succeed
        plan = Plan(**VALID_PLAN)
        planner.replan(original_plan=plan, agent_report="Report 1")
        planner.replan(original_plan=plan, agent_report="Report 2")

        # Third should raise
        with pytest.raises(Exception, match="replan"):
            planner.replan(original_plan=plan, agent_report="Report 3")

    def test_planner_splits_budget(self):
        """Sum of Task budgets must not exceed total Run budget."""
        total_max_actions = 20
        total_max_tokens = 20000

        provider = FakeProvider(responses=[make_plan_response(VALID_PLAN)])
        client = LLMClient(provider=provider)

        planner = Planner(llm_client=client)
        plan = planner.plan(
            objective="Test the checkout flow",
            target_metadata={},
            total_budget={"max_actions": total_max_actions, "max_tokens": total_max_tokens},
        )

        total_actions = sum(t.budget.get("max_actions", 0) for t in plan.tasks)
        total_tokens = sum(t.budget.get("max_tokens", 0) for t in plan.tasks)

        assert total_actions <= total_max_actions
        assert total_tokens <= total_max_tokens
