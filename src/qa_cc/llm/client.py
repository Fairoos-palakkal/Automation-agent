"""LLMClient — thin wrapper around any OpenAI-compatible provider.

Responsibilities:
- Token accounting (accumulated across calls)
- Model ID tracking
- Schema-validated calls with bounded retry (max 2 retries → 3 total attempts)
- Tool-call pass-through

The provider is dependency-injected so FakeProvider is used in tests
and the real OpenAI-compatible provider is used at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class MalformedOutputError(Exception):
    """Raised when the LLM returns unparseable output after all retry attempts."""


@dataclass
class LLMClient:
    """Wraps a provider (real or fake) and adds token accounting + schema validation.

    Args:
        provider: Any object with a `.chat(messages, **kwargs)` method that returns
                  an OpenAI-style response dict.
    """

    provider: Any
    token_usage: dict[str, int] = field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    last_model_id: str | None = None
    _max_retries: int = field(default=2, init=False, repr=False)  # 2 retries = 3 total attempts

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Call the provider and record token usage + model ID.

        Args:
            messages: OpenAI-style message list.
            **kwargs: Forwarded verbatim to the provider (e.g. tools, tool_choice).

        Returns:
            Raw provider response dict.
        """
        response = self.provider.chat(messages, **kwargs)
        self._record_usage(response)
        return response

    def chat_with_schema(
        self,
        messages: list[dict[str, Any]],
        parse_fn: Callable[[dict[str, Any]], Any],
        **kwargs: Any,
    ) -> Any:
        """Call the provider and parse the response with `parse_fn`, retrying on failure.

        Retries up to `_max_retries` times (total attempts = _max_retries + 1).

        Args:
            messages: OpenAI-style message list.
            parse_fn: Callable that accepts the raw response dict and returns a parsed value,
                      or raises an exception on malformed output.
            **kwargs: Forwarded to the provider.

        Returns:
            The value returned by `parse_fn` on the first successful parse.

        Raises:
            MalformedOutputError: when all attempts are exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            response = self.provider.chat(messages, **kwargs)
            self._record_usage(response)
            try:
                return parse_fn(response)
            except Exception as exc:
                last_exc = exc

        raise MalformedOutputError(
            f"LLM returned unparseable output after {self._max_retries + 1} attempts. "
            f"Last error: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _record_usage(self, response: dict[str, Any]) -> None:
        usage = response.get("usage", {})
        self.token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        self.token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        self.token_usage["total_tokens"] += usage.get("total_tokens", 0)
        self.last_model_id = response.get("model", self.last_model_id)
