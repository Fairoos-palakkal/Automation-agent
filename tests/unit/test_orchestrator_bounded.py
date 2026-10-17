"""Tests for Bounded Multi-Agent Orchestrator — Ticket T-17 (F-11)."""
import json
import pytest

from qa_cc.agents.api import APIAgent
from qa_cc.agents.baseline import RunResult
from qa_cc.agents.browser import BrowserAgent, TaskResult
from qa_cc.agents.orchestrator import Orchestrator
from qa_cc.agents.plan import AgentType, Plan, Task
from qa_cc.gateway.gateway import ToolGateway
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.trace.run_state import RunState
from qa_cc.trace.writer import TraceWriter
from qa_cc.verdict.evidence import Finding


class StubAgent:
    """Configurable agent returning pre-set TaskResults and recording executed tasks."""

    def __init__(self, name: str, results: list[TaskResult] = None):
        self.name = name
        self.results = list(results or [])
        self.executed_tasks: list[Task] = []
        self.new_context_calls: int = 0

    def new_context(self) -> None:
        self.new_context_calls += 1

    def execute(self, task: Task, **kwargs) -> TaskResult:
        self.executed_tasks.append(task)
        if self.results:
            return self.results.pop(0)
        return TaskResult(task_id=task.id, status="completed", actions_count=1, tokens_used=100)


class TestOrchestratorBounded:
    def test_run_level_action_cap_stops_execution(self):
        """Global max_actions on RunState halts multi-agent run when exhausted."""
        tasks = [
            Task(id=f"t{i}", goal=f"Goal {i}", assignee=AgentType.BROWSER, budget={"max_actions": 5})
            for i in range(5)
        ]
        plan = Plan(objective="Obj", tasks=tasks)

        class FakePlanner:
            def plan(self, *args, **kwargs):
                return plan

        # Each task execution consumes 5 actions
        results = [
            TaskResult(task_id=f"t{i}", status="completed", actions_count=5, tokens_used=50)
            for i in range(5)
        ]
        browser_agent = StubAgent("browser", results=results)
        api_agent = StubAgent("api")

        # Global run-level cap is 5 actions
        run_state = RunState(max_actions=5, max_tokens=10000)
        orchestrator = Orchestrator(
            planner=FakePlanner(),
            browser_agent=browser_agent,
            api_agent=api_agent,
            run_state=run_state,
        )

        res = orchestrator.run(objective="Obj", target="http://localhost:3000")

        # After 1st task executes 5 actions, run budget of 5 is exhausted
        assert len(browser_agent.executed_tasks) == 1
        assert run_state.action_count == 5
        assert res.budget_exceeded is True
        assert res.actions_count == 5

    def test_replan_triggered_on_llm_error_and_loop_terminated(self):
        """Replan is triggered on llm_error and loop_terminated statuses."""
        plan1 = Plan(
            objective="Obj",
            tasks=[Task(id="t1", goal="Task 1", assignee=AgentType.BROWSER, budget={"max_actions": 5})],
        )
        plan2 = Plan(
            objective="Obj",
            tasks=[Task(id="t2", goal="Task 2", assignee=AgentType.API, budget={"max_actions": 5})],
        )

        replan_calls = []

        class FakePlanner:
            def plan(self, *args, **kwargs):
                return plan1

            def replan(self, original_plan, agent_report, total_budget=None):
                replan_calls.append(agent_report)
                return plan2

        browser_agent = StubAgent(
            "browser",
            results=[TaskResult(task_id="t1", status="llm_error", summary="Context limit exceeded")],
        )
        api_agent = StubAgent("api", results=[TaskResult(task_id="t2", status="completed")])

        orchestrator = Orchestrator(
            planner=FakePlanner(),
            browser_agent=browser_agent,
            api_agent=api_agent,
        )

        res = orchestrator.run(objective="Obj", target="http://localhost:3000")

        assert len(replan_calls) == 1
        assert "llm_error" in replan_calls[0]
        assert len(api_agent.executed_tasks) == 1
        assert api_agent.executed_tasks[0].id == "t2"

    def test_third_failure_refuses_replan_and_traces(self, tmp_path):
        """On 3rd failed task (max_replans=2), replan is refused and traced as replan_refused."""
        trace_path = tmp_path / "trace.jsonl"
        trace_writer = TraceWriter(trace_path)

        class FakePlanner:
            def __init__(self):
                self.replan_calls = 0

            def plan(self, *args, **kwargs):
                return Plan(objective="Obj", tasks=[Task(id="t1", goal="T1", assignee=AgentType.BROWSER, budget={"max_actions": 5})])

            def replan(self, original_plan, agent_report, total_budget=None):
                self.replan_calls += 1
                next_id = f"t{self.replan_calls + 1}"
                return Plan(objective="Obj", tasks=[Task(id=next_id, goal=next_id, assignee=AgentType.BROWSER, budget={"max_actions": 5})])

        # 3 failures in a row
        browser_agent = StubAgent(
            "browser",
            results=[
                TaskResult(task_id="t1", status="failed", summary="Fail 1"),
                TaskResult(task_id="t2", status="failed", summary="Fail 2"),
                TaskResult(task_id="t3", status="failed", summary="Fail 3"),
            ],
        )

        orchestrator = Orchestrator(
            planner=FakePlanner(),
            browser_agent=browser_agent,
            api_agent=StubAgent("api"),
            trace_writer=trace_writer,
        )

        orchestrator.run(objective="Obj", target="http://localhost:3000", max_replans=2)

        entries = trace_writer.read_entries()
        refused_entries = [e for e in entries if e.get("type") == "replan_refused"]
        assert len(refused_entries) >= 1
        assert "Maximum replan limit reached" in refused_entries[0]["reason"]
        assert refused_entries[0]["task_id"] == "t3"

    def test_completed_tasks_never_rerun(self):
        """Completed tasks are never re-run even if returned in a revised Plan."""
        t1 = Task(id="t1", goal="T1", assignee=AgentType.BROWSER, budget={"max_actions": 5})
        t2 = Task(id="t2", goal="T2", assignee=AgentType.API, budget={"max_actions": 5})

        class FakePlanner:
            def plan(self, *args, **kwargs):
                return Plan(objective="Obj", tasks=[t1, t2])

            def replan(self, original_plan, agent_report, total_budget=None):
                # Replan returns t1 (already completed), t2 (which failed), and t3 (new)
                t3 = Task(id="t3", goal="T3", assignee=AgentType.BROWSER, budget={"max_actions": 5})
                return Plan(objective="Obj", tasks=[t1, t3])

        # t1 succeeds, t2 fails -> triggers replan
        browser_agent = StubAgent("browser", results=[
            TaskResult(task_id="t1", status="completed"),
            TaskResult(task_id="t3", status="completed"),
        ])
        api_agent = StubAgent("api", results=[
            TaskResult(task_id="t2", status="failed"),
        ])

        orchestrator = Orchestrator(
            planner=FakePlanner(),
            browser_agent=browser_agent,
            api_agent=api_agent,
        )

        orchestrator.run(objective="Obj", target="http://localhost:3000")

        # t1 was executed only once, never re-run
        executed_ids = [t.id for t in browser_agent.executed_tasks]
        assert executed_ids == ["t1", "t3"]

    def test_remaining_budget_passed_to_replan(self):
        """Remaining budget (total - consumed) is passed to Planner.replan."""
        captured_budget = {}

        class FakePlanner:
            def plan(self, *args, **kwargs):
                return Plan(objective="Obj", tasks=[Task(id="t1", goal="T1", assignee=AgentType.BROWSER, budget={"max_actions": 5})])

            def replan(self, original_plan, agent_report, total_budget=None):
                captured_budget.update(total_budget or {})
                return Plan(objective="Obj", tasks=[Task(id="t2", goal="T2", assignee=AgentType.API, budget={"max_actions": 5})])

        browser_agent = StubAgent(
            "browser",
            results=[TaskResult(task_id="t1", status="failed", actions_count=4, tokens_used=2000)],
        )

        run_state = RunState(max_actions=20, max_tokens=10000)
        orchestrator = Orchestrator(
            planner=FakePlanner(),
            browser_agent=browser_agent,
            api_agent=StubAgent("api"),
            run_state=run_state,
        )

        orchestrator.run(objective="Obj", target="http://localhost:3000")

        # 4 actions and 2000 tokens were consumed by t1
        assert captured_budget["max_actions"] == 16
        assert captured_budget["max_tokens"] == 8000

    def test_fresh_browser_context_called_per_task(self):
        """BrowserAgent.new_context() is invoked before executing each browser task."""
        t1 = Task(id="t1", goal="T1", assignee=AgentType.BROWSER, budget={"max_actions": 5})
        t2 = Task(id="t2", goal="T2", assignee=AgentType.BROWSER, budget={"max_actions": 5})

        class FakePlanner:
            def plan(self, *args, **kwargs):
                return Plan(objective="Obj", tasks=[t1, t2])

        browser_agent = StubAgent("browser")
        orchestrator = Orchestrator(
            planner=FakePlanner(),
            browser_agent=browser_agent,
            api_agent=StubAgent("api"),
        )

        orchestrator.run(objective="Obj", target="http://localhost:3000")

        # Two browser tasks executed -> 2 new_context calls
        assert browser_agent.new_context_calls == 2

    def test_prior_findings_rendered_in_subagent_prompts(self):
        """Prior finding summaries appear in BrowserAgent and APIAgent user prompt."""
        task = Task(
            id="t2",
            goal="Test API",
            assignee=AgentType.API,
            metadata={"prior_findings": [{"id": "F-001", "summary": "Stored XSS in search box"}]},
        )

        fake_provider = FakeProvider(responses=[{
            "id": "c1",
            "model": "fake-model",
            "choices": [{"message": {"role": "assistant", "content": "Done"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }])
        client = LLMClient(provider=fake_provider)
        gateway = ToolGateway()
        api_agent = APIAgent(llm_client=client, gateway=gateway)

        api_agent.execute(task, base_url="http://localhost:3000")

        # Verify the prompt sent to LLM included previously discovered findings
        sent_messages = fake_provider.calls[0]["messages"]
        user_message = [m["content"] for m in sent_messages if m["role"] == "user"][0]
        assert "Previously Discovered Findings (do not duplicate):" in user_message
        assert "F-001: Stored XSS in search box" in user_message
