"""FakeProvider — a deterministic stand-in for a real LLM provider.

Used in unit tests so no network, no real LLM, no tokens are consumed.
Never use in production code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ProviderExhausted(Exception):
    """Raised when FakeProvider.chat() is called after all canned responses have been consumed."""


@dataclass
class FakeProvider:
    """A canned-response queue that records every call made to it.

    Args:
        responses: Ordered list of raw response dicts to return on each `.chat()` call.
                   Each dict must follow the OpenAI chat-completion response shape.
    """

    responses: list[dict[str, Any]]
    calls: list[dict[str, Any]] = field(default_factory=list)
    _index: int = field(default=0, init=False, repr=False)

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Return the next canned response and record the call.

        Raises:
            ProviderExhausted: when the response queue is empty.
        """
        if self._index >= len(self.responses):
            raise ProviderExhausted(
                f"FakeProvider exhausted after {self._index} calls. "
                "Add more responses to the queue."
            )
        self.calls.append({"messages": messages, "kwargs": kwargs})
        response = self.responses[self._index]
        self._index += 1
        return response
