"""Multi-Agent Orchestrator — Coordinates Planner, BrowserAgent, and APIAgent (Phase 2.5).

Key architectural invariants:
- Planner runs first to produce a validated Plan.
- Sub-agents (BrowserAgent, APIAgent) execute tasks under their own isolated budgets.
- Only Findings and Evidence references are shared across sub-agents, NEVER full LLM transcripts (D6).
- If a sub-agent task fails, Orchestrator triggers Planner.replan() within the configured replan limit.
- Aggregates all discovered Findings into a unified RunResult.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from qa_cc.agents.baseline import RunResult
from qa_cc.agents.plan import AgentType, Plan, Task
from qa_cc.agents.step_log import StepLog
from qa_cc.trace.run_state import RunState
from qa_cc.trace.writer import TraceWriter
from qa_cc.verdict.evidence import Finding


class Orchestrator:
    """Coordinates multi-agent testing workflows."""

    def __init__(
        self,
        planner: Any,
        browser_agent: Any,
        api_agent: Any,
        trace_writer: Optional[TraceWriter] = None,
        run_state: Optional[RunState] = None,
        step_log: Optional[StepLog] = None,
    ):
        self.planner = planner
        self.browser_agent = browser_agent
        self.api_agent = api_agent
        self.trace_writer = trace_writer
        self.run_state = run_state or RunState()
        self.step_log = step_log or StepLog()

    def run(
        self,
        objective: str,
        target: str,
        target_metadata: Optional[Dict[str, Any]] = None,
        max_replans: int = 2,
        target_profile: Optional[Any] = None,
    ) -> RunResult:
        """Run the multi-agent QA exploration loop."""
        if self.trace_writer:
            self.trace_writer.record({
                "type": "orchestrator_start",
                "objective": objective,
                "target": target,
                "max_replans": max_replans,
                "target_profile": target_profile.to_dict() if target_profile and hasattr(target_profile, "to_dict") else None,
            })

        total_budget = {
            "max_actions": self.run_state.max_actions,
            "max_tokens": self.run_state.max_tokens,
        }

        # Step 1: Initial planning
        merged_metadata = dict(target_metadata or {})
        if target_profile:
            merged_metadata["target_profile"] = target_profile.to_dict() if hasattr(target_profile, "to_dict") else target_profile

        plan: Plan = self.planner.plan(
            objective=objective,
            target_metadata=merged_metadata,
            total_budget=total_budget,
        )

        if self.trace_writer:
            self.trace_writer.record({
                "type": "plan_generated",
                "plan": plan.model_dump() if hasattr(plan, "model_dump") else str(plan),
            })

        all_findings: List[Finding] = []
        total_actions = 0
        total_tokens = 0
        replans_used = 0
        tasks = list(plan.tasks)
        i = 0

        while i < len(tasks):
            task = tasks[i]
            i += 1

            # Pass only compact prior finding summaries, never transcripts (D6)
            task.metadata["prior_findings"] = [
                {"id": f.id, "summary": f.summary} for f in all_findings
            ]

            assignee_val = task.assignee.value if hasattr(task.assignee, "value") else str(task.assignee)
            if assignee_val == AgentType.BROWSER.value:
                task_result = self.browser_agent.execute(task, target_url=target, step_log=self.step_log)
            elif assignee_val == AgentType.API.value:
                task_result = self.api_agent.execute(task, base_url=target, step_log=self.step_log)
            else:
                task_result = self.browser_agent.execute(task, target_url=target, step_log=self.step_log)

            total_actions += getattr(task_result, "actions_count", 0)
            total_tokens += getattr(task_result, "tokens_used", 0)

            # Record subagent completion in trace
            if self.trace_writer:
                self.trace_writer.record({
                    "type": "subagent_task_completed",
                    "task_id": task.id,
                    "assignee": assignee_val,
                    "status": task_result.status,
                    "findings_count": len(task_result.findings),
                })

            # Collect findings
            for finding in task_result.findings:
                all_findings.append(finding)
                self.run_state.add_finding(finding)

            # Check if task failed and replanning is allowed
            if task_result.status == "failed" and replans_used < max_replans:
                report = task_result.summary or f"Task {task.id} failed"
                try:
                    revised_plan = self.planner.replan(
                        original_plan=plan,
                        agent_report=report,
                        total_budget=total_budget,
                    )
                    replans_used += 1
                    # Replace remaining tasks with new plan's tasks
                    tasks = list(revised_plan.tasks)
                    i = 0
                    if self.trace_writer:
                        self.trace_writer.record({
                            "type": "plan_revised",
                            "plan": revised_plan.model_dump() if hasattr(revised_plan, "model_dump") else str(revised_plan),
                        })
                except Exception:
                    pass

        return RunResult(
            findings=all_findings,
            actions_count=total_actions,
            tokens_used=total_tokens,
            budget_exceeded=self.run_state.action_count >= self.run_state.max_actions,
            loop_recovery_triggered=False,
            trace_path=str(self.trace_writer._path) if self.trace_writer else None,
            summary=f"Orchestrated multi-agent run completed: {len(all_findings)} findings",
            step_log=self.step_log,
        )
