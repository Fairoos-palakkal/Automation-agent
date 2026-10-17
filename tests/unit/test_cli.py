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

    def test_cli_results_empty_directory_exits_one(self, tmp_path):
        """CLI results in an empty directory exits status code 1 with 'no scored runs found'."""
        empty_runs = tmp_path / "empty_runs"
        empty_runs.mkdir()
        cmd = [sys.executable, "-m", "qa_cc", "results", "--runs-dir", str(empty_runs)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 1
        output = proc.stdout + proc.stderr
        assert "no scored runs found" in output.lower()

    def test_cli_results_aggregates_score_json_fixtures(self, tmp_path):
        """CLI results aggregates score.json files across runs/<config>/<run_id>/."""
        runs_dir = tmp_path / "runs"
        base_1 = runs_dir / "baseline" / "run_1"
        base_2 = runs_dir / "baseline" / "run_2"
        multi_1 = runs_dir / "multi_agent" / "run_1"
        base_1.mkdir(parents=True)
        base_2.mkdir(parents=True)
        multi_1.mkdir(parents=True)

        s1 = {
            "recall": 0.60,
            "total_defects": 5,
            "matched_defects": ["DEFECT-001", "DEFECT-002", "DEFECT-003"],
            "replay_rate": 1.0,
            "precision": 1.0,
            "unsupported_findings": 0,
            "actions": 14,
            "tokens": 18000,
            "is_held_out": False,
        }
        s2 = {
            "recall": 0.80,
            "total_defects": 5,
            "matched_defects": ["DEFECT-001", "DEFECT-002", "DEFECT-003", "DEFECT-004"],
            "replay_rate": 1.0,
            "precision": 1.0,
            "unsupported_findings": 0,
            "actions": 16,
            "tokens": 20000,
            "is_held_out": False,
        }
        sm1 = {
            "recall": 0.80,
            "total_defects": 5,
            "matched_defects": ["DEFECT-001", "DEFECT-002", "DEFECT-003", "DEFECT-004"],
            "replay_rate": 1.0,
            "precision": 1.0,
            "unsupported_findings": 0,
            "actions": 22,
            "tokens": 35000,
            "is_held_out": False,
        }
        (base_1 / "score.json").write_text(json.dumps(s1))
        (base_2 / "score.json").write_text(json.dumps(s2))
        (multi_1 / "score.json").write_text(json.dumps(sm1))

        cmd = [sys.executable, "-m", "qa_cc", "results", "--runs-dir", str(runs_dir), "--format", "table"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        assert "baseline" in proc.stdout.lower()
        assert "multi_agent" in proc.stdout.lower()
        # Mean of 60% and 80% is 70.0%
        assert "70.0%" in proc.stdout

    def test_cli_results_changing_fixture_changes_output(self, tmp_path):
        """Modifying a fixture score.json changes the aggregated results table."""
        runs_dir = tmp_path / "runs"
        base_1 = runs_dir / "baseline" / "run_1"
        base_1.mkdir(parents=True)

        s1 = {
            "recall": 0.40,
            "total_defects": 5,
            "matched_defects": ["DEFECT-001", "DEFECT-002"],
            "replay_rate": 1.0,
            "precision": 1.0,
            "unsupported_findings": 0,
            "actions": 10,
            "tokens": 12000,
            "is_held_out": False,
        }
        score_file = base_1 / "score.json"
        score_file.write_text(json.dumps(s1))

        cmd = [sys.executable, "-m", "qa_cc", "results", "--runs-dir", str(runs_dir), "--format", "table"]
        proc1 = subprocess.run(cmd, capture_output=True, text=True)
        assert "40.0%" in proc1.stdout

        # Now change score.json
        s1["recall"] = 1.00
        score_file.write_text(json.dumps(s1))

        proc2 = subprocess.run(cmd, capture_output=True, text=True)
        assert "100.0%" in proc2.stdout
        assert "40.0%" not in proc2.stdout

    def test_cli_results_json_format_and_held_out(self, tmp_path):
        """CLI results --format json outputs valid json and respects --include-held-out."""
        runs_dir = tmp_path / "runs"
        base_1 = runs_dir / "baseline" / "run_1"
        held_1 = runs_dir / "held_out" / "run_1"
        base_1.mkdir(parents=True)
        held_1.mkdir(parents=True)

        (base_1 / "score.json").write_text(json.dumps({
            "recall": 0.60,
            "total_defects": 5,
            "matched_defects": ["DEFECT-001"],
            "is_held_out": False,
            "actions": 12,
            "tokens": 15000,
        }))
        (held_1 / "score.json").write_text(json.dumps({
            "recall": 0.33,
            "total_defects": 3,
            "matched_defects": ["DEFECT-006"],
            "is_held_out": True,
            "actions": 20,
            "tokens": 30000,
        }))

        # Without --include-held-out
        cmd1 = [sys.executable, "-m", "qa_cc", "results", "--runs-dir", str(runs_dir), "--format", "json"]
        proc1 = subprocess.run(cmd1, capture_output=True, text=True)
        assert proc1.returncode == 0
        data1 = json.loads(proc1.stdout)
        configs1 = [c["name"] for c in data1["benchmark_results"]]
        assert "baseline" in configs1
        assert "held_out" not in configs1

        # With --include-held-out
        cmd2 = [sys.executable, "-m", "qa_cc", "results", "--runs-dir", str(runs_dir), "--format", "json", "--include-held-out"]
        proc2 = subprocess.run(cmd2, capture_output=True, text=True)
        assert proc2.returncode == 0
        data2 = json.loads(proc2.stdout)
        configs2 = [c["name"] for c in data2["benchmark_results"]]
        assert "baseline" in configs2
        assert "held_out" in configs2

    def test_cli_score_juice_shop(self, tmp_path, monkeypatch):
        """CLI score with --target-type juice_shop queries scoreboard reader, scores, and does NOT stamp verdicts."""
        from unittest.mock import patch
        run_dir = tmp_path / "js_run"
        run_dir.mkdir()
        findings = [
            {
                "id": "F-1",
                "summary": "Search endpoint returns 500 SQLite syntax error",
                "evidence": [{"type": "dom_snapshot", "content": "500 Error: SQLITE_ERROR"}],
            }
        ]
        (run_dir / "findings.json").write_text(json.dumps(findings))

        mock_challenges = [
            {"id": 1, "key": "errorHandlingChallenge", "name": "Error Handling", "solved": True},
            {"id": 2, "key": "scoreBoardChallenge", "name": "Score Board", "solved": False},
        ]

        with patch("benchmark.scoring.juice_shop.JuiceShopScoreboardReader.fetch_challenges", return_value=mock_challenges):
            ret = main(["score", "--run-dir", str(run_dir), "--target-type", "juice_shop"])
            assert ret == 0

            # Findings must NOT be modified with verdicts (ADR-0001, ADR-0003, T-07)
            raw = json.loads((run_dir / "findings.json").read_text())
            assert raw[0].get("verdict") is None

            # score.json must be written
            score_data = json.loads((run_dir / "score.json").read_text())
            assert "Error Handling" in score_data["matched_defects"]

    def test_no_verdict_creation_in_cli(self):
        """Invariant T-07: cli.py contains zero invocations of Verdict(."""
        cli_path = Path("src/qa_cc/cli.py")
        content = cli_path.read_text(encoding="utf-8")
        assert "Verdict(" not in content

