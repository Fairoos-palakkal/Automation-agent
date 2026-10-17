"""AgentLoop — Unified execution loop for Baseline, Browser, and API agents (Phase 6, T-08/T-09).

Eliminates loop duplication and guarantees uniform:
1. Budget checking and RunState accounting.
2. StepLog recording of executed actions and observations with step IDs.
3. Structured error handling: records llm_error, tool_error, and invalid_args in trace and status.
4. Tool call parsing rejecting malformed JSON arguments instead of executing empty dicts.
5. Loop detection and recovery handling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable, Dict, List, Optional

from qa_cc.agents.loop_detector import (
    LoopDetector,
    RecoveryAction,
    compute_action_fingerprint,
    compute_observation_fingerprint,
)
from qa_cc.agents.step_log import StepLog
from qa_cc.gateway.gateway import ToolGateway
from qa_cc.llm.client import LLMClient
from qa_cc.trace.run_state import RunState, BudgetExceeded
from qa_cc.trace.writer import TraceWriter
from qa_cc.verdict.evidence import Evidence, EvidenceType, Finding


@dataclass
class AgentLoopResult:
    """Unified result container produced by AgentLoop."""

    findings: List[Finding] = field(default_factory=list)
    actions_count: int = 0
    tokens_used: int = 0
    budget_exceeded: bool = False
    loop_recovery_triggered: bool = False
    trace_path: Optional[str] = None
    summary: str = ""
    status: str = "completed"  # completed, llm_error, tool_error, invalid_args, budget_exceeded, failed
    steps: List[Dict[str, Any]] = field(default_factory=list)

    def to_run_result(self, is_mock: bool = False):
        from qa_cc.agents.baseline import RunResult
        return RunResult(
            findings=self.findings,
            actions_count=self.actions_count,
            tokens_used=self.tokens_used,
            budget_exceeded=self.budget_exceeded,
            loop_recovery_triggered=self.loop_recovery_triggered,
            trace_path=self.trace_path,
            summary=self.summary,
            is_mock=is_mock,
            status=self.status,
        )

    def to_task_result(self, task_id: str):
        from qa_cc.agents.browser import TaskResult
        return TaskResult(
            task_id=task_id,
            status=self.status,
            findings=self.findings,
            steps=self.steps,
            summary=self.summary,
            actions_count=self.actions_count,
            tokens_used=self.tokens_used,
            budget_exceeded=self.budget_exceeded,
            loop_recovery_triggered=self.loop_recovery_triggered,
        )


class AgentLoop:
    """Unified autonomous agent loop."""

    def __init__(
        self,
        client: LLMClient,
        gateway: ToolGateway,
        tools: List[Dict[str, Any]],
        system_prompt: str,
        run_state: Optional[RunState] = None,
        step_log: Optional[StepLog] = None,
        trace_writer: Optional[TraceWriter] = None,
        loop_detector: Optional[LoopDetector] = None,
        verdict_engine: Optional[Any] = None,
        agent_name: str = "baseline",
        task_id: Optional[str] = None,
        finding_handler: Optional[Callable[..., Finding]] = None,
    ) -> None:
        self.client = client
        self.gateway = gateway
        self.tools = tools
        self.system_prompt = system_prompt
        self.run_state = run_state if run_state is not None else RunState()
        self.step_log = step_log if step_log is not None else StepLog()
        self.trace_writer = trace_writer
        self.loop_detector = loop_detector if loop_detector is not None else LoopDetector(threshold=3)
        self.verdict_engine = verdict_engine
        self.agent_name = agent_name
        self.task_id = task_id
        self.finding_handler = finding_handler
        self._loop_recovery_triggered = False

    def run(
        self,
        objective: str = "",
        target: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
        max_turns: int = 25,
        extra_user_content: Optional[str] = None,
    ) -> AgentLoopResult:
        """Execute the agent loop up to max_turns."""
        if messages is None:
            user_content = extra_user_content or f"Objective: {objective}\nTarget URL: {target}"
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_content},
            ]

        current_url = target
        last_obs = ""
        budget_exceeded = False
        summary = ""
        status = "completed"

        if self.trace_writer and self.agent_name == "baseline":
            self.trace_writer.record({
                "type": "run_start",
                "objective": objective,
                "target": target,
                "model_id": getattr(getattr(self.client, "provider", None), "model", "unknown"),
                "tokens": 0,
            })

        for _ in range(max_turns):
            try:
                self.run_state.check_budget()
            except BudgetExceeded:
                budget_exceeded = True
                status = "budget_exceeded"
                break

            try:
                response = self.client.chat(messages, tools=self.tools)
            except Exception as e:
                status = "llm_error"
                summary = f"LLM error: {e}"
                if self.trace_writer:
                    self.trace_writer.record({
                        "type": "llm_error",
                        "agent": self.agent_name,
                        "task_id": self.task_id,
                        "error": str(e),
                        "model_id": getattr(getattr(self.client, "provider", None), "model", "unknown"),
                        "tokens": 0,
                    })
                break

            usage = response.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            self.run_state.record_tokens(tokens)

            if self.trace_writer:
                trace_type = "subagent_model_call" if self.agent_name in ("browser", "api") else "model_call"
                record_payload: Dict[str, Any] = {
                    "type": trace_type,
                    "model_id": response.get("model", getattr(getattr(self.client, "provider", None), "model", "unknown")),
                    "tokens": tokens,
                    "usage": usage,
                }
                if self.task_id:
                    record_payload["task_id"] = self.task_id
                    record_payload["agent"] = self.agent_name
                self.trace_writer.record(record_payload)

            choice = response.get("choices", [{}])[0]
            msg = choice.get("message", {})
            messages.append(msg)

            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                if msg.get("content"):
                    summary = msg.get("content")
                break

            finished = False
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name")
                raw_args = func.get("arguments", {})

                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except Exception as err:
                        # Malformed tool argument JSON: reject and trace
                        if self.trace_writer:
                            self.trace_writer.record({
                                "type": "invalid_args",
                                "agent": self.agent_name,
                                "task_id": self.task_id,
                                "tool_name": tool_name,
                                "raw_args": raw_args,
                                "error": str(err),
                                "model_id": response.get("model", "unknown"),
                                "tokens": 0,
                            })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", "tc-err"),
                            "name": tool_name or "unknown",
                            "content": f"Error: Malformed JSON arguments for tool '{tool_name}': {err}",
                        })
                        continue
                else:
                    args = raw_args or {}

                if tool_name == "finish":
                    summary = args.get("summary", "Exploration concluded")
                    finished = True
                    break

                if tool_name == "report_finding":
                    if self.finding_handler:
                        finding = self.finding_handler(args, current_url, tc)
                    else:
                        finding = self._create_finding(args, current_url)

                    self.run_state.add_finding(finding)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", "tc-1"),
                        "name": tool_name,
                        "content": f"Finding recorded: {finding.id}",
                    })
                    continue

                # Normal tool execution (browser, http, etc.)
                action_fp = compute_action_fingerprint(tool_name, args, current_url)
                obs_fp = compute_observation_fingerprint(last_obs)

                loop_action = self.loop_detector.check(action_fp, obs_fp)
                if loop_action in (RecoveryAction.RE_OBSERVE, RecoveryAction.TRY_ALTERNATE):
                    self._loop_recovery_triggered = True
                elif loop_action == RecoveryAction.TERMINATE_INCONCLUSIVE:
                    self._loop_recovery_triggered = True
                    finished = True
                    break

                try:
                    self.run_state.check_budget()
                    self.run_state.record_action(action_fp)
                except BudgetExceeded:
                    budget_exceeded = True
                    status = "budget_exceeded"
                    finished = True
                    break

                url_before = current_url
                try:
                    res = self.gateway.execute(tool_name, args)
                    url_after = current_url
                    if isinstance(res, dict) and "url" in res:
                        current_url = res["url"]
                        url_after = current_url
                    if isinstance(res, dict) and "snapshot" in res:
                        last_obs = res["snapshot"]

                    self.step_log.record_step(
                        tool=tool_name,
                        args=args,
                        url_before=url_before,
                        url_after=url_after,
                        ok=True,
                        result=res,
                    )
                    res_str = json.dumps(res, default=str) if isinstance(res, (dict, list)) else str(res)
                except Exception as e:
                    self.step_log.record_step(
                        tool=tool_name,
                        args=args,
                        url_before=url_before,
                        url_after=url_before,
                        ok=False,
                        error=str(e),
                    )
                    if self.trace_writer:
                        self.trace_writer.record({
                            "type": "tool_error",
                            "agent": self.agent_name,
                            "task_id": self.task_id,
                            "tool_name": tool_name,
                            "args": args,
                            "error": str(e),
                            "model_id": getattr(getattr(self.client, "provider", None), "model", "unknown"),
                            "tokens": 0,
                        })
                    res_str = f"Error executing {tool_name}: {e}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "tc-1"),
                    "name": tool_name,
                    "content": res_str,
                })

            if finished:
                break

        return AgentLoopResult(
            findings=self.run_state.findings,
            actions_count=self.run_state.actions_count,
            tokens_used=self.run_state.tokens_count,
            budget_exceeded=budget_exceeded,
            loop_recovery_triggered=self._loop_recovery_triggered,
            trace_path=str(self.trace_writer._path) if self.trace_writer else None,
            summary=summary or f"{self.agent_name.capitalize()} execution finished",
            status=status,
            steps=self.step_log.get_step_dicts(),
        )

    def _create_finding(self, args: Dict[str, Any], current_url: str) -> Finding:
        ev_type_str = args.get("evidence_type", "dom_snapshot")
        try:
            ev_type = EvidenceType(ev_type_str)
        except ValueError:
            ev_type = EvidenceType.DOM_SNAPSHOT

        ev_metadata = {"url": current_url, "agent": self.agent_name, "task_id": self.task_id}
        if self.agent_name == "api":
            ev_metadata["base_url"] = current_url

        ev = Evidence(
            type=ev_type,
            content=args.get("evidence_content", ""),
            metadata=ev_metadata,
        )

        # Concrete StepLog steps if available, else fingerprints for backwards compatibility
        step_dicts = self.step_log.get_step_dicts()
        if not step_dicts:
            step_dicts = [
                {"fingerprint": fp} if isinstance(fp, str) else fp
                for fp in self.run_state.history
            ]

        finding_id = f"F-{self.task_id + '-' if self.task_id else ''}{len(self.run_state.findings) + 1}"
        default_summary = "API Defect discovered" if self.agent_name == "api" else "Defect discovered"
        finding_metadata = {"agent": self.agent_name, "task_id": self.task_id}
        if self.agent_name:
            finding_metadata["assignee"] = self.agent_name

        return Finding(
            id=finding_id,
            summary=args.get("summary", default_summary),
            evidence=[ev],
            steps=step_dicts,
            metadata=finding_metadata,
        )

