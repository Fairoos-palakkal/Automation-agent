"""Multi-Agent Orchestrator — Coordinates Planner, BrowserAgent, and APIAgent (Phase 2.5).

Key architectural invariants:
- Planner runs first to produce a validated Plan.
- Sub-agents (BrowserAgent, APIAgent) execute tasks under their own isolated budgets.
- Only Findings and Evidence references are shared across sub-agents, NEVER full LLM transcripts (D6).
- If a sub-agent task fails, Orchestrator triggers Planner.replan() within the configured replan limit.
- Aggregates all discovered Findings into a unified RunResult.
"""
from __future__ import annotations

import json
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
        completed_task_ids: set[str] = set()
        tasks: List[Task] = list(plan.tasks)
        i = 0

        while i < len(tasks):
            # Enforce global run-level budget before starting each task
            if (
                self.run_state.action_count >= self.run_state.max_actions
                or self.run_state.token_count > self.run_state.max_tokens
            ):
                break

            task = tasks[i]
            i += 1

            # Skip completed tasks (never re-run completed task IDs)
            if task.id in completed_task_ids:
                continue

            # Pass only compact prior finding summaries, never transcripts (D6)
            task.metadata["prior_findings"] = [
                {"id": f.id, "summary": f.summary} for f in all_findings
            ]

            assignee_val = task.assignee.value if hasattr(task.assignee, "value") else str(task.assignee)
            if assignee_val == AgentType.BROWSER.value:
                if hasattr(self.browser_agent, "new_context"):
                    self.browser_agent.new_context()
                task_result = self.browser_agent.execute(task, target_url=target, step_log=self.step_log)
            elif assignee_val == AgentType.API.value:
                task_result = self.api_agent.execute(task, base_url=target, step_log=self.step_log)
            else:
                if hasattr(self.browser_agent, "new_context"):
                    self.browser_agent.new_context()
                task_result = self.browser_agent.execute(task, target_url=target, step_log=self.step_log)

            actions_used = getattr(task_result, "actions_count", 0)
            tokens_used = getattr(task_result, "tokens_used", 0)
            total_actions += actions_used
            total_tokens += tokens_used

            # Charge every TaskResult to the run-level RunState
            for _ in range(actions_used):
                self.run_state.record_action(f"task-{task.id}")
            self.run_state.record_tokens(tokens_used)

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

            if task_result.status == "completed":
                completed_task_ids.add(task.id)

            # Check if task failed or hit terminal condition and replanning is needed
            if task_result.status in ("failed", "loop_terminated", "llm_error"):
                report = json.dumps({
                    "task_id": task.id,
                    "status": task_result.status,
                    "summary": task_result.summary or f"Task {task.id} failed",
                    "findings_count": len(task_result.findings),
                    "completed_tasks": list(completed_task_ids),
                })

                if replans_used < max_replans:
                    remaining_budget = {
                        "max_actions": max(0, self.run_state.max_actions - self.run_state.action_count),
                        "max_tokens": max(0, self.run_state.max_tokens - self.run_state.token_count),
                    }
                    try:
                        revised_plan = self.planner.replan(
                            original_plan=plan,
                            agent_report=report,
                            total_budget=remaining_budget,
                        )
                        replans_used += 1
                        # Filter out completed tasks so they never re-run
                        new_tasks = [t for t in revised_plan.tasks if t.id not in completed_task_ids]
                        tasks = new_tasks
                        i = 0
                        if self.trace_writer:
                            self.trace_writer.record({
                                "type": "plan_revised",
                                "plan": revised_plan.model_dump() if hasattr(revised_plan, "model_dump") else str(revised_plan),
                                "replan_count": replans_used,
                            })
                    except Exception as exc:
                        if self.trace_writer:
                            self.trace_writer.record({
                                "type": "replan_refused",
                                "reason": str(exc),
                                "task_id": task.id,
                                "replans_used": replans_used,
                            })
                else:
                    # 3rd failure or max_replans reached: refuse replan and trace
                    if self.trace_writer:
                        self.trace_writer.record({
                            "type": "replan_refused",
                            "reason": f"Maximum replan limit reached ({max_replans})",
                            "task_id": task.id,
                            "status": task_result.status,
                            "replans_used": replans_used,
                        })

            # Check global run budget after charging
            if (
                self.run_state.action_count >= self.run_state.max_actions
                or self.run_state.token_count > self.run_state.max_tokens
            ):
                break

        budget_exceeded = (
            self.run_state.action_count >= self.run_state.max_actions
            or self.run_state.token_count > self.run_state.max_tokens
        )

        return RunResult(
            findings=all_findings,
            actions_count=total_actions,
            tokens_used=total_tokens,
            budget_exceeded=budget_exceeded,
            loop_recovery_triggered=False,
            trace_path=str(self.trace_writer._path) if self.trace_writer else None,
            summary=f"Orchestrated multi-agent run completed: {len(all_findings)} findings",
            step_log=self.step_log,
        )

