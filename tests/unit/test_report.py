"""Tests for Static HTML Report Generator — Phase 1.9 (Red -> Green)."""
import tempfile
from pathlib import Path
import pytest

from qa_cc.agents.baseline import RunResult
from qa_cc.report.generator import generate_report
from qa_cc.verdict.evidence import Finding, Evidence, EvidenceType, Verdict, VerdictType


class TestReportGenerator:
    def test_report_generates_html(self, tmp_path):
        """generate_report produces a valid HTML file at target location."""
        output_file = tmp_path / "report.html"
        result = RunResult(
            findings=[],
            actions_count=3,
            tokens_used=150,
            summary="Test run complete",
        )

        generate_report(result, output_path=output_file)
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "<html" in content
        assert "Agentic QA Command Center" in content

    def test_report_contains_findings(self, tmp_path):
        """Report contains summaries, evidence references, and verdicts of all findings."""
        output_file = tmp_path / "findings_report.html"
        finding = Finding(
            id="F-101",
            summary="Broken button in navbar",
            evidence=[Evidence(type=EvidenceType.SCREENSHOT, content="artifacts/shot1.png")],
            verdict=Verdict(type=VerdictType.FAIL, reason="Element unclickable"),
        )
        result = RunResult(findings=[finding], actions_count=5, tokens_used=300)

        generate_report(result, output_path=output_file)
        content = output_file.read_text(encoding="utf-8")

        assert "F-101" in content
        assert "Broken button in navbar" in content
        assert "FAIL" in content
        assert "artifacts/shot1.png" in content
