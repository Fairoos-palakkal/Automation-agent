"""Tests for LLMClient — Phase 0.3 (Red → Green)"""
import pytest
from qa_cc.llm.client import LLMClient, MalformedOutputError
from qa_cc.llm.fake_provider import FakeProvider, ProviderExhausted


def make_response(
    content="ok",
    model="fake-1",
    prompt_tokens=10,
    completion_tokens=5,
    tool_calls=None,
):
    choice = {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
    if tool_calls:
        choice["message"]["tool_calls"] = tool_calls
    return {
        "id": "fake-id",
        "model": model,
        "choices": [choice],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


class TestLLMClient:
    def test_llm_client_returns_assistant_message(self):
        """client.chat(messages) returns a response with role='assistant'."""
        provider = FakeProvider(responses=[make_response("Hello")])
        client = LLMClient(provider=provider)

        result = client.chat([{"role": "user", "content": "Hi"}])

        assert result["choices"][0]["message"]["role"] == "assistant"
        assert result["choices"][0]["message"]["content"] == "Hello"

    def test_llm_client_records_token_counts(self):
        """After a call, client.token_usage reflects prompt + completion tokens."""
        provider = FakeProvider(responses=[make_response(prompt_tokens=20, completion_tokens=8)])
        client = LLMClient(provider=provider)

        client.chat([{"role": "user", "content": "Hi"}])

        assert client.token_usage["prompt_tokens"] == 20
        assert client.token_usage["completion_tokens"] == 8
        assert client.token_usage["total_tokens"] == 28

    def test_llm_client_accumulates_token_counts_across_calls(self):
        """Token usage accumulates across multiple calls."""
        provider = FakeProvider(responses=[
            make_response(prompt_tokens=10, completion_tokens=5),
            make_response(prompt_tokens=20, completion_tokens=10),
        ])
        client = LLMClient(provider=provider)

        client.chat([{"role": "user", "content": "first"}])
        client.chat([{"role": "user", "content": "second"}])

        assert client.token_usage["prompt_tokens"] == 30
        assert client.token_usage["completion_tokens"] == 15
        assert client.token_usage["total_tokens"] == 45

    def test_llm_client_records_model_id(self):
        """The response includes the served model ID from the provider."""
        provider = FakeProvider(responses=[make_response(model="qwen3-8b-flash")])
        client = LLMClient(provider=provider)

        result = client.chat([{"role": "user", "content": "Hi"}])

        assert result["model"] == "qwen3-8b-flash"
        assert client.last_model_id == "qwen3-8b-flash"

    def test_llm_client_retries_malformed_output(self):
        """If provider returns invalid JSON for a schema-validated call, client retries up to 2 times."""
        bad = make_response(content="not-valid-json{{{")
        good = make_response(content='{"result": "ok"}')
        provider = FakeProvider(responses=[bad, good])
        client = LLMClient(provider=provider)

        import json

        def parse(r):
            return json.loads(r["choices"][0]["message"]["content"])

        result = client.chat_with_schema(
            messages=[{"role": "user", "content": "Give me JSON"}],
            parse_fn=parse,
        )

        assert result == {"result": "ok"}
        assert len(provider.calls) == 2  # retried once

    def test_llm_client_fails_after_max_retries(self):
        """3 consecutive malformed responses → MalformedOutputError."""
        bad = make_response(content="BAD")
        provider = FakeProvider(responses=[bad, bad, bad])
        client = LLMClient(provider=provider)

        import json

        def parse(r):
            return json.loads(r["choices"][0]["message"]["content"])

        with pytest.raises(MalformedOutputError):
            client.chat_with_schema(
                messages=[{"role": "user", "content": "Give me JSON"}],
                parse_fn=parse,
            )

        assert len(provider.calls) == 3

    def test_llm_client_tool_calling(self):
        """client passes tool definitions and receives tool call responses."""
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "navigate", "arguments": '{"url": "https://example.com"}'},
            }
        ]
        provider = FakeProvider(responses=[make_response(tool_calls=tool_calls)])
        client = LLMClient(provider=provider)
        tools = [{"type": "function", "function": {"name": "navigate"}}]

        result = client.chat(
            [{"role": "user", "content": "Go to example.com"}],
            tools=tools,
        )

        assert result["choices"][0]["message"]["tool_calls"] == tool_calls
        assert provider.calls[0]["kwargs"]["tools"] == tools
