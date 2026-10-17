"""Unit tests for T-05: Runtime Secret and Token Scrubbing on the Live Path (Red Phase)."""
import os
import json
import pytest
from qa_cc.security.scrubber import Scrubber
from qa_cc.trace.writer import TraceWriter
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.verdict.evidence import Finding, Evidence, EvidenceType
from qa_cc.agents.baseline import RunResult
from qa_cc.report.generator import generate_report


@pytest.fixture
def test_secrets(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-secret-agent-key-99999")
    monkeypatch.setenv("CUSTOM_AUTH_SECRET", "super-secret-custom-pass")
    return {
        "api_key": "sk-secret-agent-key-99999",
        "custom": "super-secret-custom-pass",
        "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.G3j0v8gR",
    }


def test_scrubber_replaces_env_secrets_and_jwt(test_secrets):
    """Scrubber replaces environment variables, Bearer tokens, and JWT strings."""
    scrubber = Scrubber(secret_env_vars=["LLM_API_KEY", "CUSTOM_AUTH_SECRET"])

    raw_text = (
        f"Connecting with key {test_secrets['api_key']} and Bearer my_bearer_token_xyz "
        f"and token {test_secrets['jwt']} end"
    )
    scrubbed = scrubber.scrub(raw_text)

    assert test_secrets["api_key"] not in scrubbed
    assert "my_bearer_token_xyz" not in scrubbed
    assert test_secrets["jwt"] not in scrubbed
    assert "[SCRUBBED]" in scrubbed


def test_scrubber_scrubs_dictionary_headers(test_secrets):
    """Headers such as Authorization, Cookie, and Set-Cookie are scrubbed in dicts."""
    scrubber = Scrubber()
    headers = {
        "Authorization": "Bearer secret_jwt_or_key_here",
        "Set-Cookie": "session_id=12345; Secure; HttpOnly",
        "Cookie": "jwt=eyJabc.def.ghi",
        "Content-Type": "application/json",
    }
    scrubbed = scrubber.scrub(headers)

    assert scrubbed["Authorization"] == "[SCRUBBED]"
    assert scrubbed["Set-Cookie"] == "[SCRUBBED]"
    assert scrubbed["Cookie"] == "[SCRUBBED]"
    assert scrubbed["Content-Type"] == "application/json"


def test_tool_gateway_uses_shared_scrubber(test_secrets, tmp_path):
    """ToolGateway passes arguments and results through the shared scrubber into trace."""
    trace_path = tmp_path / "trace.jsonl"
    scrubber = Scrubber(secret_env_vars=["LLM_API_KEY"])
    trace_writer = TraceWriter(path=trace_path, scrubber=scrubber)
    gateway = ToolGateway(trace_writer=trace_writer, scrubber=scrubber)

    def dummy_tool(token: str):
        return {"status": "ok", "echo_token": token, "session": test_secrets["jwt"]}

    gateway.register_tool(ToolDefinition(name="auth_tool", handler=dummy_tool))
    gateway.execute("auth_tool", {"token": test_secrets["api_key"]})

    entries = trace_writer.read_entries()
    assert len(entries) == 1
    raw_trace = trace_path.read_text(encoding="utf-8")
    assert test_secrets["api_key"] not in raw_trace
    assert test_secrets["jwt"] not in raw_trace


def test_findings_and_report_zero_secret_leakage(test_secrets, tmp_path):
    """Findings serialization and report generation scrub all secrets from output files."""
    scrubber = Scrubber(secret_env_vars=["LLM_API_KEY"])

    finding = Finding(
        id="F-SEC-1",
        summary=f"Found leak with {test_secrets['api_key']}",
        evidence=[
            Evidence(
                type=EvidenceType.NETWORK_REQUEST,
                content=f"POST /login -> response: {test_secrets['jwt']}",
                metadata={"auth": f"Bearer {test_secrets['api_key']}"},
            )
        ],
    )
    run_result = RunResult(findings=[finding], actions_count=1, tokens_used=10)

    # Serialize findings
    findings_file = tmp_path / "findings.json"
    scrubbed_findings_data = [scrubber.scrub(f.model_dump()) for f in run_result.findings]
    findings_file.write_text(json.dumps(scrubbed_findings_data), encoding="utf-8")

    # Generate report
    report_file = tmp_path / "report.html"
    generate_report(run_result, output_path=report_file, scrubber=scrubber)

    findings_content = findings_file.read_text(encoding="utf-8")
    report_content = report_file.read_text(encoding="utf-8")

    assert test_secrets["api_key"] not in findings_content
    assert test_secrets["jwt"] not in findings_content
    assert test_secrets["api_key"] not in report_content
    assert test_secrets["jwt"] not in report_content


def test_cli_mock_run_zero_secret_leakage(test_secrets, tmp_path):
    """Executing a mock run with API keys yields zero secret matches across the run directory."""
    from qa_cc.cli import main

    out_dir = tmp_path / "run_out"
    ret = main([
        "run",
        "--mock",
        "--target", "http://localhost:3000",
        "--objective", "Verify secrets are never leaked",
        "--output-dir", str(out_dir),
    ])
    assert ret == 0

    # Walk through all generated files
    for fpath in out_dir.rglob("*"):
        if fpath.is_file():
            text = fpath.read_text(encoding="utf-8", errors="ignore")
            assert test_secrets["api_key"] not in text, f"Secret leaked into {fpath}"
            assert test_secrets["custom"] not in text, f"Secret leaked into {fpath}"
