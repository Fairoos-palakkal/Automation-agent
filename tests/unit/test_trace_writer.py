"""Tests for TraceWriter — Phase 0.4 (Red → Green)"""
import json
import os
import tempfile
from pathlib import Path

import pytest

from qa_cc.trace.writer import TraceWriter


class TestTraceWriter:
    def test_trace_writer_creates_jsonl_file(self, tmp_path):
        """After .record(entry), the file exists and contains valid JSON per line."""
        trace_file = tmp_path / "trace.jsonl"
        writer = TraceWriter(path=trace_file)

        writer.record({"type": "model_call", "model_id": "fake-1", "tokens": 10})

        assert trace_file.exists()
        lines = trace_file.read_text().strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["type"] == "model_call"

    def test_trace_entry_has_required_fields(self, tmp_path):
        """Each entry has timestamp, type, model_id, tokens."""
        trace_file = tmp_path / "trace.jsonl"
        writer = TraceWriter(path=trace_file)

        writer.record({"type": "model_call", "model_id": "fake-1", "tokens": 10})

        parsed = json.loads(trace_file.read_text().strip())
        assert "timestamp" in parsed
        assert "type" in parsed
        assert "model_id" in parsed
        assert "tokens" in parsed

    def test_trace_writer_scrubs_secrets(self, tmp_path, monkeypatch):
        """An entry containing a secret env var value is scrubbed to [SCRUBBED]."""
        monkeypatch.setenv("SECRET_KEY", "super-secret-abc123")
        trace_file = tmp_path / "trace.jsonl"
        writer = TraceWriter(path=trace_file, secret_env_vars=["SECRET_KEY"])

        writer.record({
            "type": "tool_call",
            "model_id": "fake-1",
            "tokens": 0,
            "args": {"api_key": "super-secret-abc123"},
        })

        content = trace_file.read_text()
        assert "super-secret-abc123" not in content
        assert "[SCRUBBED]" in content

    def test_trace_writer_records_tool_calls(self, tmp_path):
        """Tool call entries include tool name, args, and result."""
        trace_file = tmp_path / "trace.jsonl"
        writer = TraceWriter(path=trace_file)

        writer.record({
            "type": "tool_call",
            "model_id": "fake-1",
            "tokens": 0,
            "tool": "navigate",
            "args": {"url": "https://example.com"},
            "result": {"snapshot": "<html>...</html>"},
        })

        parsed = json.loads(trace_file.read_text().strip())
        assert parsed["tool"] == "navigate"
        assert parsed["args"]["url"] == "https://example.com"
        assert "result" in parsed

    def test_trace_writer_multiple_entries(self, tmp_path):
        """N .record() calls produce N lines."""
        trace_file = tmp_path / "trace.jsonl"
        writer = TraceWriter(path=trace_file)

        for i in range(5):
            writer.record({"type": "model_call", "model_id": "fake-1", "tokens": i, "seq": i})

        lines = trace_file.read_text().strip().splitlines()
        assert len(lines) == 5
        for i, line in enumerate(lines):
            assert json.loads(line)["seq"] == i
