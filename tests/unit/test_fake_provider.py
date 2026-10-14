"""Tests for FakeProvider — Phase 0.2 (Red → Green)"""
import pytest
from qa_cc.llm.fake_provider import FakeProvider, ProviderExhausted


def make_response(content="Hello", model="fake-model-1", prompt_tokens=10, completion_tokens=5):
    return {
        "id": "fake-id",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens},
    }


class TestFakeProvider:
    def test_fake_provider_returns_canned_response(self):
        """Calling FakeProvider.chat(messages) returns the pre-configured response."""
        response = make_response("Hello!")
        provider = FakeProvider(responses=[response])
        messages = [{"role": "user", "content": "Hi"}]

        result = provider.chat(messages)

        assert result == response

    def test_fake_provider_records_calls(self):
        """After N calls, FakeProvider.calls has N entries with messages."""
        r1 = make_response("First")
        r2 = make_response("Second")
        provider = FakeProvider(responses=[r1, r2])

        provider.chat([{"role": "user", "content": "msg1"}])
        provider.chat([{"role": "user", "content": "msg2"}])

        assert len(provider.calls) == 2
        assert provider.calls[0]["messages"] == [{"role": "user", "content": "msg1"}]
        assert provider.calls[1]["messages"] == [{"role": "user", "content": "msg2"}]

    def test_fake_provider_raises_on_empty_queue(self):
        """Calling when no responses remain raises ProviderExhausted."""
        provider = FakeProvider(responses=[make_response()])
        provider.chat([{"role": "user", "content": "first"}])

        with pytest.raises(ProviderExhausted):
            provider.chat([{"role": "user", "content": "second"}])

    def test_fake_provider_records_tool_kwargs(self):
        """Calls are recorded including any extra kwargs (e.g. tools, tool_choice)."""
        response = make_response()
        provider = FakeProvider(responses=[response])
        tools = [{"type": "function", "function": {"name": "navigate"}}]

        provider.chat([{"role": "user", "content": "go"}], tools=tools)

        assert provider.calls[0]["kwargs"]["tools"] == tools
