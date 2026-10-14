"""Tests for CLI Entry Point — Phase 1.9 (Red -> Green)."""
import subprocess
import sys
from pathlib import Path
import pytest

from qa_cc.cli import main


class TestCLI:
    def test_cli_help_exits_zero(self):
        """CLI --help flag exits with status code 0."""
        cmd = [sys.executable, "-m", "qa_cc", "--help"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        assert "Agentic QA Command Center" in proc.stdout or "usage:" in proc.stdout

    def test_cli_run_command_help_exits_zero(self):
        """CLI run --help command exits with status code 0."""
        cmd = [sys.executable, "-m", "qa_cc", "run", "--help"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        assert "--target" in proc.stdout
        assert "--objective" in proc.stdout

    def test_cli_run_produces_trace_and_report(self, tmp_path):
        """CLI run in mock/test mode creates trace file and static HTML report."""
        out_dir = tmp_path / "run_out"
        cmd = [
            sys.executable,
            "-m",
            "qa_cc",
            "run",
            "--target",
            "http://localhost:3000",
            "--objective",
            "Sanity test",
            "--output-dir",
            str(out_dir),
            "--mock",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        assert (out_dir / "trace.jsonl").exists()
        assert (out_dir / "report.html").exists()
