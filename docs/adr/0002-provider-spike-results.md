# Provider Spike Results & Configuration (ADR 0002)

## Status
Decided / Documented.

## Context
Per PRD §8 and Phase 0.6:
The system uses an OpenAI-compatible interface (`OpenAICompatibleProvider`).
Two profiles are supported:
- **`dev` profile:** Gemini free tier / OmniRoute / local mock; served model may vary, used for rapid local iteration.
- **`bench` profile:** Pinned model (e.g. Qwen3.8-Flash via B.AI), thinking off or low, strictly tracked token usage.

Unit tests never connect to the real network or LLM (they use `FakeProvider` and deterministic cassettes). Real provider contract tests are isolated under `tests/contract/test_provider_contract.py` with `@pytest.mark.live`.

## Contract Test Protocol
To execute the live contract test:
```bash
export LLM_BASE_URL="<endpoint>"
export LLM_API_KEY="<api-key>"
export LLM_MODEL="<pinned-model-id>"
pytest tests/contract/ -v -m live
```

## Spike Invariants Verified
1. OpenAI-compatible `chat.completions.create` endpoint accepts standard messages format.
2. Function / tool calling schema (`tools=[{"type": "function", ...}]`, `tool_choice="auto"`) returns structured assistant messages with `tool_calls`.
3. Token usage (`prompt_tokens`, `completion_tokens`, `total_tokens`) and served `model` are extracted and recorded on every call.
4. Schema validation with bounded retry (max 2 retries) handles occasional malformed JSON without crashing the agent.
