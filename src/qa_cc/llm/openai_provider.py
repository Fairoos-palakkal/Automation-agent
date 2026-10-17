"""OpenAICompatibleProvider — wraps the openai SDK for any OpenAI-compatible endpoint.

Used at runtime (dev and bench profiles). Never used in unit tests — use FakeProvider instead.

Rule: model and base URL come from profiles (dev, bench).
Rule: Pin the model in the bench profile. Record served model ID and token counts in every trace entry.
Rule: Secrets come from environment variables only.
"""
from __future__ import annotations

import time
from typing import Any, Callable


class OpenAICompatibleProvider:
    """Calls any OpenAI-compatible chat completion endpoint.

    Args:
        base_url: API base URL (e.g. https://api.openai.com/v1).
        api_key: Authentication key. Must come from an environment variable — never hardcoded.
        model: Model ID to send in every request.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retries on transient errors (429, 5xx).
        backoff_factor: Multiplier for exponential backoff delay.
        sleep_fn: Injectable sleep function for testing without delay.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        try:
            from openai import OpenAI  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "openai package is required for OpenAICompatibleProvider. "
                "Install it with: uv pip install openai"
            ) from exc

        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.sleep_fn = sleep_fn

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Send a chat completion request with exponential backoff on transient errors."""
        kwargs.pop("model", None)  # always use the pinned model
        attempt = 0

        while True:
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    **kwargs,
                )
                return response.model_dump()
            except Exception as e:
                status_code = getattr(e, "status_code", None)
                if status_code is None:
                    resp = getattr(e, "response", None)
                    status_code = getattr(resp, "status_code", None)

                is_transient = (
                    status_code in (429, 500, 502, 503, 504)
                    or "rate limit" in str(e).lower()
                    or "429" in str(e)
                    or "500" in str(e)
                    or "timeout" in str(e).lower()
                    or "connection" in str(e).lower()
                )

                if is_transient and attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** attempt)
                    self.sleep_fn(sleep_time)
                    attempt += 1
                else:
                    raise e
