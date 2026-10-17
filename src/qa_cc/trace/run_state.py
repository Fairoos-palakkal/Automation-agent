"""RunState — the mutable context passed through every agent turn.

Tracks budgets (actions, tokens), findings, and action fingerprints for loop detection.
Raising BudgetExceeded is the enforcement mechanism; agents must call check_budget()
after every action.

This module contains no I/O and no LLM calls — it is always deterministic.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


class BudgetExceeded(Exception):
    """Raised by RunState.check_budget() when any budget limit is exceeded."""


@dataclass
class RunState:
    """Mutable per-Run state: budgets, findings, fingerprints.

    Args:
        max_actions: Maximum number of tool calls allowed in this Run.
        max_tokens: Maximum token count allowed in this Run.
        max_model_calls: Maximum LLM chat invocations allowed.
        max_duration_seconds: Wall-clock duration budget limit.
    """

    max_actions: int = 25
    max_tokens: int = 100_000
    max_model_calls: Optional[int] = None
    max_duration_seconds: Optional[float] = None
    action_count: int = 0
    token_count: int = 0
    model_calls_count: int = 0
    start_time: Optional[float] = None
    findings: list[Any] = field(default_factory=list)
    _fingerprints: set[str] = field(default_factory=set, repr=False)
    history: list[str] = field(default_factory=list)

    @property
    def actions_count(self) -> int:
        return self.action_count

    @property
    def tokens_count(self) -> int:
        return self.token_count

    def start_timer(self) -> None:
        if self.start_time is None:
            self.start_time = time.monotonic()

    def check_budget(self) -> None:
        """Raise BudgetExceeded if any limit is breached."""
        if self.action_count >= self.max_actions:
            raise BudgetExceeded(
                f"action budget exceeded: {self.action_count} >= {self.max_actions}"
            )
        if self.token_count > self.max_tokens:
            raise BudgetExceeded(
                f"token budget exceeded: {self.token_count} > {self.max_tokens}"
            )
        if self.max_model_calls is not None and self.model_calls_count >= self.max_model_calls:
            raise BudgetExceeded(
                f"model-call budget exceeded: {self.model_calls_count} >= {self.max_model_calls}"
            )
        if self.max_duration_seconds is not None and self.start_time is not None:
            elapsed = time.monotonic() - self.start_time
            if elapsed > self.max_duration_seconds:
                raise BudgetExceeded(
                    f"wall-clock duration budget exceeded: {elapsed:.2f}s > {self.max_duration_seconds}s"
                )

    def record_model_call(self) -> None:
        """Record an LLM model invocation."""
        if self.start_time is None:
            self.start_timer()
        self.model_calls_count += 1

    def remaining_turns(self, default_max: int = 25) -> int:
        """Calculate maximum turns that can be executed within remaining budget."""
        remaining = default_max
        remaining = min(remaining, max(0, self.max_actions - self.action_count))
        if self.max_model_calls is not None:
            remaining = min(remaining, max(0, self.max_model_calls - self.model_calls_count))
        return max(0, remaining)

    def record_action(self, fingerprint: str) -> None:
        """Increment action count and store the action fingerprint.

        Args:
            fingerprint: A deterministic hash identifying this action+observation pair.
        """
        self.action_count += 1
        self._fingerprints.add(fingerprint)
        self.history.append(fingerprint)

    def record_tokens(self, count: int) -> None:
        """Add `count` tokens to the running total.

        Args:
            count: Number of tokens to add (prompt + completion from one LLM call).
        """
        self.token_count += count

    def add_finding(self, finding: Any) -> None:
        """Append a Finding to the findings list.

        Args:
            finding: Any Finding dict or model instance.
        """
        self.findings.append(finding)

    def has_fingerprint(self, fingerprint: str) -> bool:
        """Return True if this fingerprint has been seen in the current Run.

        Args:
            fingerprint: Fingerprint to look up.
        """
        return fingerprint in self._fingerprints
