"""Unit tests for T-06: Fail-Fast Initialization and Provider Error Handling (Red Phase)."""
from unittest.mock import MagicMock, patch
import pytest
from qa_cc.cli import main
from qa_cc.llm.openai_provider import OpenAICompatibleProvider
from qa_cc.agents.baseline import RunResult
from qa_cc.report.generator import generate_report


def test_run_without_llm_api_key_exits_nonzero(monkeypatch, capsys):
    """Running qa-cc run without LLM_API_KEY exits with non-zero status and explicit error."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with patch("dotenv.load_dotenv"):
        ret = main(["run", "--target", "http://localhost:3000", "--objective", "Test fail fast"])
        assert ret == 1
        captured = capsys.readouterr()
        assert "LLM_API_KEY" in captured.err or "LLM_API_KEY" in captured.out


def test_missing_browser_fails_fast(monkeypatch, capsys, tmp_path):
    """Missing browser binaries fail immediately rather than continuing with empty toolset."""
    monkeypatch.setenv("LLM_API_KEY", "sk-valid-test-key")

    with patch("playwright.sync_api.sync_playwright") as mock_pw:
        mock_instance = MagicMock()
        mock_pw.return_value.start.return_value = mock_instance
        mock_instance.chromium.launch.side_effect = Exception("Executable doesn't exist: chromium")

        ret = main([
            "run",
            "--target", "http://localhost:3000",
            "--objective", "Test browser missing",
            "--output-dir", str(tmp_path / "browser_fail_out"),
        ])

        assert ret == 1
        captured = capsys.readouterr()
        assert "browser" in captured.err.lower() or "playwright" in captured.err.lower()


def test_openai_provider_retries_transient_errors():
    """Transient 429 and 500 errors trigger retry with backoff and eventually succeed."""
    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        # Simulate 429, then 500, then success
        class DummyRateLimitError(Exception):
            status_code = 429

        class DummyServerError(Exception):
            status_code = 500

        mock_resp = MagicMock()
        mock_resp.model_dump.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Success after retry"}}],
            "usage": {"total_tokens": 15},
        }

        sleep_calls = []
        mock_client.chat.completions.create.side_effect = [
            DummyRateLimitError("Rate limit exceeded"),
            DummyServerError("Internal Server Error"),
            mock_resp,
        ]

        provider = OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            model="test-model",
            max_retries=3,
            backoff_factor=0.01,
            sleep_fn=lambda s: sleep_calls.append(s),
        )

        res = provider.chat([{"role": "user", "content": "hi"}])
        assert res["choices"][0]["message"]["content"] == "Success after retry"
        assert len(sleep_calls) == 2
        assert mock_client.chat.completions.create.call_count == 3


def test_reports_from_mock_runs_display_prominent_badge(tmp_path):
    """Reports generated from mock runs display a prominent MOCK RUN badge."""
    output_file = tmp_path / "mock_report.html"
    run_res = RunResult(findings=[], actions_count=2, tokens_used=20, is_mock=True)

    generate_report(run_res, output_path=output_file)
    content = output_file.read_text(encoding="utf-8")

    assert "MOCK RUN" in content
