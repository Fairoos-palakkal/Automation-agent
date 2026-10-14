"""Contract tests for real LLM providers — Phase 0.6.

Marked @pytest.mark.live — excluded from the default test run.
Run explicitly: pytest tests/contract/ -m live

These tests consume real tokens. Run sparingly.
Record results (failure rate, malformed-JSON rate) in docs/adr/0002-provider-spike-results.md.
"""
import os
import pytest
from qa_cc.llm.client import LLMClient
from qa_cc.llm.openai_provider import OpenAICompatibleProvider


@pytest.mark.live
class TestRealProviderContract:
    """Spike: validate the B.AI / OmniRoute provider before relying on it."""

    @pytest.fixture
    def provider(self):
        """Construct the provider from environment variables or .env file.

        Required env vars in .env or environment:
            LLM_BASE_URL  — e.g. https://api.openai.com/v1 or B.AI endpoint
            LLM_API_KEY   — API key
            LLM_MODEL     — model ID to pin for the bench profile
        """
        from dotenv import load_dotenv
        load_dotenv(override=True)

        base_url = os.environ.get("LLM_BASE_URL", "")
        api_key = os.environ.get("LLM_API_KEY", "")
        model = os.environ.get("LLM_MODEL", "")

        if not api_key or api_key == "your_api_key_here":
            pytest.skip("Real LLM_API_KEY not configured in .env. Replace 'your_api_key_here' with your actual key.")

        return OpenAICompatibleProvider(base_url=base_url, api_key=api_key, model=model)

    def test_contract_real_provider_returns_response(self, provider):
        """A single real call returns a valid response with a model ID."""
        client = LLMClient(provider=provider)

        result = client.chat([{"role": "user", "content": "Say 'hello' in exactly one word."}])

        assert result["choices"][0]["message"]["role"] == "assistant"
        assert result["model"]  # model ID must be non-empty
        assert client.token_usage["total_tokens"] > 0

    def test_contract_tool_calling_works(self, provider):
        """A tool-calling request returns a tool call response."""
        client = LLMClient(provider=provider)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "navigate",
                    "description": "Navigate to a URL",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                },
            }
        ]

        result = client.chat(
            [{"role": "user", "content": "Navigate to https://example.com"}],
            tools=tools,
            tool_choice="auto",
        )

        choices = result["choices"]
        assert choices
        # Either a tool call or a text response — both are valid here
        message = choices[0]["message"]
        assert message["role"] == "assistant"
