"""Tests for Evidence and Finding models — Phase 1.3 (Red -> Green)."""
import pytest
from pydantic import ValidationError

from qa_cc.verdict.evidence import Evidence, Finding, EvidenceType


class TestEvidenceModel:
    def test_evidence_requires_type_and_content(self):
        """Creating Evidence without required fields raises ValidationError."""
        with pytest.raises(ValidationError):
            Evidence()

        ev = Evidence(type=EvidenceType.SCREENSHOT, content="artifacts/screenshot_1.png")
        assert ev.type == EvidenceType.SCREENSHOT
        assert ev.content == "artifacts/screenshot_1.png"

    def test_evidence_serializes_to_dict(self):
        """Evidence model serializes to dict with all expected fields."""
        ev = Evidence(
            type=EvidenceType.CONSOLE_LOG,
            content="TypeError: Cannot read properties of undefined",
            metadata={"source": "catalog.html"},
        )
        d = ev.model_dump()
        assert d["type"] == "console_log"
        assert d["content"] == "TypeError: Cannot read properties of undefined"
        assert d["metadata"] == {"source": "catalog.html"}
        assert "timestamp" in d

    def test_finding_requires_evidence(self):
        """A Finding without at least one Evidence raises ValidationError."""
        with pytest.raises(ValidationError):
            Finding(
                id="F-1",
                summary="Catalog filter broken",
                evidence=[],
            )

        ev = Evidence(type=EvidenceType.CONSOLE_LOG, content="TypeError")
        f = Finding(
            id="F-1",
            summary="Catalog filter broken",
            evidence=[ev],
        )
        assert len(f.evidence) == 1
        assert f.id == "F-1"

    def test_finding_has_no_verdict_initially(self):
        """A newly created Finding has verdict=None initially."""
        ev = Evidence(type=EvidenceType.DOM_SNAPSHOT, content="<div>Error</div>")
        f = Finding(
            id="F-2",
            summary="Unexpected banner",
            evidence=[ev],
        )
        assert f.verdict is None
