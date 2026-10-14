"""RunState — the mutable context passed through every agent turn.

Tracks budgets (actions, tokens), findings, and action fingerprints for loop detection.
Raising BudgetExceeded is the enforcement mechanism; agents must call check_budget()
after every action.

This module contains no I/O and no LLM calls — it is always deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class BudgetExceeded(Exception):
    """Raised by RunState.check_budget() when any budget limit is exceeded."""


@dataclass
class RunState:
    """Mutable per-Run state: budgets, findings, fingerprints.

    Args:
        max_actions: Maximum number of tool calls allowed in this Run.
        max_tokens: Maximum token count allowed in this Run.
    """

    max_actions: int = 25
    max_tokens: int = 100_000
    action_count: int = 0
    token_count: int = 0
    findings: list[Any] = field(default_factory=list)
    _fingerprints: set[str] = field(default_factory=set, repr=False)
    history: list[str] = field(default_factory=list)

    @property
    def actions_count(self) -> int:
        return self.action_count

    @property
    def tokens_count(self) -> int:
        return self.token_count

    def check_budget(self) -> None:
        """Raise BudgetExceeded if any limit is breached.

        Raises:
            BudgetExceeded: with a message naming which budget was exceeded.
        """
        if self.action_count >= self.max_actions:
            raise BudgetExceeded(
                f"action budget exceeded: {self.action_count} >= {self.max_actions}"
            )
        if self.token_count > self.max_tokens:
            raise BudgetExceeded(
                f"token budget exceeded: {self.token_count} > {self.max_tokens}"
            )

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
