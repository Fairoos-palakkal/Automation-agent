"""Tests for CLI Entry Point — Phase 1.9 (Red -> Green)."""
import json
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

    def test_cli_multi_agent_run_produces_artifacts(self, tmp_path):
        """CLI run with --multi-agent produces trace, findings, and report."""
        out_dir = tmp_path / "multi_agent_out"
        cmd = [
            sys.executable,
            "-m",
            "qa_cc",
            "run",
            "--target",
            "http://localhost:3000",
            "--objective",
            "Multi-agent test",
            "--output-dir",
            str(out_dir),
            "--mock",
            "--multi-agent",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        assert (out_dir / "trace.jsonl").exists()
        assert (out_dir / "findings.json").exists()
        assert (out_dir / "report.html").exists()

    def test_cli_score_compare(self, tmp_path):
        """CLI score --compare prints side-by-side comparison of two runs."""
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"
        dir1.mkdir()
        dir2.mkdir()

        f1 = [{
            "id": "F-1",
            "summary": "Missing email validation on contact form",
            "evidence": [{"type": "dom_snapshot", "content": "err"}],
        }]
        f2 = [
            {
                "id": "F-1",
                "summary": "Missing email validation on contact form",
                "evidence": [{"type": "dom_snapshot", "content": "err"}],
            },
            {
                "id": "F-2",
                "summary": "Unhandled TypeError on catalog filter",
                "evidence": [{"type": "console_log", "content": "TypeError: Cannot read properties of undefined"}],
            },
        ]
        (dir1 / "findings.json").write_text(json.dumps(f1))
        (dir2 / "findings.json").write_text(json.dumps(f2))

        cmd = [
            sys.executable,
            "-m",
            "qa_cc",
            "score",
            "--run-dir",
            str(dir1),
            "--compare",
            str(dir2),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        assert "COMPARISON" in proc.stdout or "Run 1" in proc.stdout

    def test_cli_results_table_format(self):
        """CLI results --format table prints benchmark comparison table."""
        cmd = [sys.executable, "-m", "qa_cc", "results", "--format", "table"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        assert "BENCHMARK RESULTS" in proc.stdout or "Recall" in proc.stdout
        assert "Baseline" in proc.stdout
        assert "Multi-Agent" in proc.stdout

    def test_cli_results_include_held_out(self):
        """CLI results --include-held-out includes held-out defects in summary."""
        cmd = [sys.executable, "-m", "qa_cc", "results", "--include-held-out"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        assert "Held-Out" in proc.stdout

    def test_cli_results_json_format(self):
        """CLI results --format json outputs valid json."""
        cmd = [sys.executable, "-m", "qa_cc", "results", "--format", "json"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert "benchmark_results" in data

