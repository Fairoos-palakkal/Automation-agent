"""OpenAICompatibleProvider — wraps the openai SDK for any OpenAI-compatible endpoint.

Used at runtime (dev and bench profiles). Never used in unit tests — use FakeProvider instead.

Rule: model and base URL come from profiles (dev, bench).
Rule: Pin the model in the bench profile. Record served model ID and token counts in every trace entry.
Rule: Secrets come from environment variables only.
"""
from __future__ import annotations

from typing import Any


class OpenAICompatibleProvider:
    """Calls any OpenAI-compatible chat completion endpoint.

    Args:
        base_url: API base URL (e.g. https://api.openai.com/v1).
        api_key: Authentication key. Must come from an environment variable — never hardcoded.
        model: Model ID to send in every request.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
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

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Send a chat completion request and return the raw response as a dict.

        Args:
            messages: OpenAI-style message list.
            **kwargs: Forwarded to the API (e.g. tools, tool_choice).

        Returns:
            Response serialised as a plain dict (model_dump()).
        """
        kwargs.pop("model", None)  # always use the pinned model
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            **kwargs,
        )
        return response.model_dump()
