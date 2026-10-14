"""Tests for Multi-Agent Orchestrator — Phase 2.5 (Red → Green)."""
import pytest

from qa_cc.agents.api import APIAgent
from qa_cc.agents.baseline import RunResult
from qa_cc.agents.browser import BrowserAgent, TaskResult
from qa_cc.agents.orchestrator import Orchestrator
from qa_cc.agents.plan import Plan, Task, AgentType
from qa_cc.agents.planner import Planner
from qa_cc.gateway.gateway import ToolGateway
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.trace.run_state import RunState
from qa_cc.verdict.evidence import Evidence, EvidenceType, Finding


class MockAgent:
    """Mock sub-agent to record calls and simulate execution."""

    def __init__(self, name: str, results: list[TaskResult] = None):
        self.name = name
        self.results = results or []
        self.executed_tasks: list[Task] = []

    def execute(self, task: Task, **kwargs) -> TaskResult:
        self.executed_tasks.append(task)
        if self.results:
            return self.results.pop(0)
        return TaskResult(task_id=task.id, status="completed", summary=f"{self.name} completed")


class TestOrchestrator:
    def test_orchestrator_calls_planner_then_agents(self):
        """Planner runs first to generate Plan, then sub-agents execute assigned Tasks."""
        plan = Plan(
            objective="Full system test",
            tasks=[
                Task(id="t1", goal="Browser test", assignee=AgentType.BROWSER, budget={"max_actions": 5}),
                Task(id="t2", goal="API test", assignee=AgentType.API, budget={"max_actions": 5}),
            ],
        )

        class FakePlanner:
            def __init__(self):
                self.planned = False

            def plan(self, objective, target_metadata=None, total_budget=None):
                self.planned = True
                return plan

        planner = FakePlanner()
        browser_agent = MockAgent("browser")
        api_agent = MockAgent("api")

        orchestrator = Orchestrator(
            planner=planner,
            browser_agent=browser_agent,
            api_agent=api_agent,
        )
        result = orchestrator.run(objective="Full system test", target="http://localhost:3000")

        assert planner.planned is True
        assert len(browser_agent.executed_tasks) == 1
        assert browser_agent.executed_tasks[0].id == "t1"
        assert len(api_agent.executed_tasks) == 1
        assert api_agent.executed_tasks[0].id == "t2"
        assert isinstance(result, RunResult)

    def test_orchestrator_separate_budgets(self):
        """Each sub-agent runs with its own Task-specific budget from the Plan."""
        t1 = Task(id="t1", goal="B", assignee=AgentType.BROWSER, budget={"max_actions": 4, "max_tokens": 4000})
        t2 = Task(id="t2", goal="A", assignee=AgentType.API, budget={"max_actions": 8, "max_tokens": 8000})
        plan = Plan(objective="Obj", tasks=[t1, t2])

        class FakePlanner:
            def plan(self, *args, **kwargs):
                return plan

        browser_agent = MockAgent("browser")
        api_agent = MockAgent("api")

        orchestrator = Orchestrator(
            planner=FakePlanner(),
            browser_agent=browser_agent,
            api_agent=api_agent,
        )
        orchestrator.run(objective="Obj", target="http://localhost:3000")

        assert browser_agent.executed_tasks[0].budget["max_actions"] == 4
        assert api_agent.executed_tasks[0].budget["max_actions"] == 8

    def test_orchestrator_collects_all_findings(self):
        """Findings from all sub-agents are aggregated into the final RunResult."""
        f1 = Finding(
            id="F-1",
            summary="UI bug",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<div>err</div>")],
        )
        f2 = Finding(
            id="F-2",
            summary="API bug",
            evidence=[Evidence(type=EvidenceType.NETWORK_REQUEST, content="500")],
        )

        plan = Plan(
            objective="Obj",
            tasks=[
                Task(id="t1", goal="B", assignee=AgentType.BROWSER, budget={"max_actions": 5}),
                Task(id="t2", goal="A", assignee=AgentType.API, budget={"max_actions": 5}),
            ],
        )

        class FakePlanner:
            def plan(self, *args, **kwargs):
                return plan

        browser_agent = MockAgent("browser", results=[TaskResult(task_id="t1", findings=[f1])])
        api_agent = MockAgent("api", results=[TaskResult(task_id="t2", findings=[f2])])

        orchestrator = Orchestrator(
            planner=FakePlanner(),
            browser_agent=browser_agent,
            api_agent=api_agent,
        )
        result = orchestrator.run(objective="Obj", target="http://localhost:3000")

        assert len(result.findings) == 2
        summaries = [f.summary for f in result.findings]
        assert "UI bug" in summaries
        assert "API bug" in summaries

    def test_orchestrator_shares_findings_not_transcripts(self):
        """Shared context between agents contains only Findings / Evidence refs, never transcripts (D6)."""
        f1 = Finding(
            id="F-1",
            summary="Bug 1",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<p>Err</p>")],
        )
        plan = Plan(
            objective="Obj",
            tasks=[
                Task(id="t1", goal="Task 1", assignee=AgentType.BROWSER, budget={"max_actions": 5}),
                Task(id="t2", goal="Task 2", assignee=AgentType.API, budget={"max_actions": 5}),
            ],
        )

        class FakePlanner:
            def plan(self, *args, **kwargs):
                return plan

        browser_agent = MockAgent("browser", results=[TaskResult(task_id="t1", findings=[f1])])
        api_agent = MockAgent("api", results=[TaskResult(task_id="t2")])

        orchestrator = Orchestrator(
            planner=FakePlanner(),
            browser_agent=browser_agent,
            api_agent=api_agent,
        )
        orchestrator.run(objective="Obj", target="http://localhost:3000")

        # Second task received shared context if metadata is passed
        second_task = api_agent.executed_tasks[0]
        shared = second_task.metadata.get("prior_findings", [])
        # Only IDs or summaries, never raw message dictionaries
        for item in shared:
            assert isinstance(item, (str, dict))
            if isinstance(item, dict):
                assert "role" not in item

    def test_orchestrator_replan_flow(self):
        """On sub-agent failure, Orchestrator triggers Planner.replan with agent report."""
        plan1 = Plan(
            objective="Obj",
            tasks=[
                Task(id="t1", goal="Task 1", assignee=AgentType.BROWSER, budget={"max_actions": 5}),
            ],
        )
        plan2 = Plan(
            objective="Obj",
            tasks=[
                Task(id="t2", goal="Recovery Task", assignee=AgentType.API, budget={"max_actions": 5}),
            ],
        )

        class FakePlanner:
            def __init__(self):
                self.replanned = False

            def plan(self, *args, **kwargs):
                return plan1

            def replan(self, original_plan, agent_report, total_budget=None):
                self.replanned = True
                assert "Task 1 failed" in agent_report
                return plan2

        planner = FakePlanner()
        # First task fails
        browser_agent = MockAgent(
            "browser",
            results=[TaskResult(task_id="t1", status="failed", summary="Task 1 failed due to timeout")],
        )
        api_agent = MockAgent("api", results=[TaskResult(task_id="t2", status="completed")])

        orchestrator = Orchestrator(
            planner=planner,
            browser_agent=browser_agent,
            api_agent=api_agent,
        )
        result = orchestrator.run(objective="Obj", target="http://localhost:3000")

        assert planner.replanned is True
        assert len(api_agent.executed_tasks) == 1
        assert api_agent.executed_tasks[0].id == "t2"
