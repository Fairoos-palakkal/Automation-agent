"""Tests for ScoringHarness — Phase 1.8 (Red -> Green)."""
import json
import tempfile
from pathlib import Path
import pytest

from benchmark.scoring.harness import (
    ScoringHarness,
    ScoreReport,
    MismatchedModelError,
)
from qa_cc.verdict.evidence import Finding, Evidence, EvidenceType


@pytest.fixture
def mock_defects_file(tmp_path):
    defects = [
        {
            "id": "DEFECT-001",
            "set": "tuning",
            "page": "/contact.html",
            "description": "Missing email validation",
            "keywords": ["email", "contact"],
        },
        {
            "id": "DEFECT-002",
            "set": "tuning",
            "page": "/index.html",
            "description": "Broken pricing link",
            "keywords": ["pricing", "404", "broken"],
        },
        {
            "id": "DEFECT-003",
            "set": "tuning",
            "page": "/catalog.html",
            "description": "Catalog filter TypeError",
            "keywords": ["filter", "TypeError"],
        },
        {
            "id": "DEFECT-004",
            "set": "tuning",
            "page": "/cart.html",
            "description": "Negative cart total",
            "keywords": ["negative", "cart", "total"],
        },
        {
            "id": "DEFECT-005",
            "set": "tuning",
            "page": "/index.html",
            "description": "Missing accessible name on button",
            "keywords": ["accessible", "aria", "subscribe"],
        },
        {
            "id": "DEFECT-006",
            "set": "held_out",
            "page": "/checkout.html",
            "description": "Modal overlay unclickable",
            "keywords": ["overlay", "checkout"],
        },
    ]
    gt_path = tmp_path / "defects.json"
    gt_path.write_text(json.dumps(defects), encoding="utf-8")
    return gt_path


class TestScoringHarness:
    def test_recall_calculation(self, mock_defects_file):
        """3 matched defects out of 5 tuning defects produces recall = 0.6."""
        harness = ScoringHarness(ground_truth_path=mock_defects_file)

        findings = [
            Finding(
                id="F-1",
                summary="Email validation missing on contact form",
                evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="form", metadata={"url": "/contact.html"})],
            ),
            Finding(
                id="F-2",
                summary="Broken pricing link returns 404",
                evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="404", metadata={"url": "/index.html"})],
            ),
            Finding(
                id="F-3",
                summary="Catalog filter button throws TypeError",
                evidence=[Evidence(type=EvidenceType.CONSOLE_LOG, content="TypeError", metadata={"url": "/catalog.html"})],
            ),
        ]

        report = harness.score(findings=findings)
        assert report.recall == 0.6  # 3 / 5
        assert len(report.matched_defects) == 3

    def test_precision_unmatched_findings_flagged(self, mock_defects_file):
        """Findings matching no known planted defect are flagged for manual triage."""
        harness = ScoringHarness(ground_truth_path=mock_defects_file)

        findings = [
            Finding(
                id="F-1",
                summary="Some random cosmetic font size issue",
                evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<p>font</p>")],
            ),
        ]

        report = harness.score(findings=findings)
        assert len(report.unmatched_findings) == 1
        assert report.unmatched_findings[0].id == "F-1"

    def test_replay_rate_calculation(self, mock_defects_file):
        """Calculates share of Findings whose steps reproduce the defect upon replay."""
        harness = ScoringHarness(ground_truth_path=mock_defects_file)
        replay_results = {"F-1": True, "F-2": True, "F-3": False}

        report = harness.score(findings=[], replay_results=replay_results)
        assert pytest.approx(report.replay_rate, 0.01) == 0.67

    def test_scoring_uses_tuning_set_only(self, mock_defects_file):
        """By default, held-out defects are excluded from the denominator in scoring."""
        harness = ScoringHarness(ground_truth_path=mock_defects_file)

        # Matched the held-out defect DEFECT-006
        findings = [
            Finding(
                id="F-held",
                summary="Modal overlay on checkout page blocks clicking",
                evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="overlay", metadata={"url": "/checkout.html"})],
            )
        ]

        report = harness.score(findings=findings, include_held_out=False)
        # Denominator should be 5 (tuning), not 6
        assert report.total_defects == 5
        # Held-out defect was not counted in tuning recall
        assert report.recall == 0.0

    def test_scoring_refuses_mismatched_bench_model(self, mock_defects_file):
        """Comparing runs against an expected bench model ID raises MismatchedModelError on divergence."""
        harness = ScoringHarness(ground_truth_path=mock_defects_file)

        with pytest.raises(MismatchedModelError):
            harness.score(
                findings=[],
                expected_model="Qwen3.8-Flash",
                actual_model="gpt-4o-mini",
            )

    def test_scoring_juice_shop_technical_summaries(self, mock_defects_file):
        """Juice Shop scoring matches technical defect descriptions (500 SQL error, admin SQLi login)."""
        harness = ScoringHarness(ground_truth_path=mock_defects_file)
        challenges = [
            {"id": 1, "key": "errorHandlingChallenge", "name": "Error Handling", "solved": True},
            {"id": 2, "key": "scoreBoardChallenge", "name": "Score Board", "solved": False},
            {"id": 3, "key": "loginAdminChallenge", "name": "Login Admin", "solved": True},
        ]
        findings = [
            Finding(
                id="F-1",
                summary="Search endpoint /rest/products/search returns HTTP 500 with exposed SQLite error details when given SQL metacharacters",
                evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="500 Error: SQLITE_ERROR: near UNION: syntax error")],
            ),
            Finding(
                id="F-2",
                summary="SQL Injection authentication bypass on the /rest/user/login endpoint with admin@juice-sh.op",
                evidence=[Evidence(type=EvidenceType.SCREENSHOT, content="login")],
            ),
            Finding(
                id="F-3",
                summary="Unrelated UI button alignment is off by 2px",
                evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="button")],
            ),
        ]
        report = harness.score(findings=findings, target_type="juice_shop", scoreboard_challenges=challenges)
        assert len(report.unmatched_findings) == 1
        assert report.unmatched_findings[0].id == "F-3"
        assert "Error Handling" in report.matched_defects
        assert "Login Admin" in report.matched_defects
