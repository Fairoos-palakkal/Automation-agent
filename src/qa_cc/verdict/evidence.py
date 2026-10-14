"""Evidence and Finding models — core data structures for deterministic assertions and replay."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class EvidenceType(str, Enum):
    SCREENSHOT = "screenshot"
    CONSOLE_LOG = "console_log"
    DOM_SNAPSHOT = "dom_snapshot"
    NETWORK_REQUEST = "network_request"
    ASSERTION_CHECK = "assertion_check"


class VerdictType(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    FLAKY = "FLAKY"


class Evidence(BaseModel):
    type: EvidenceType
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Verdict(BaseModel):
    type: VerdictType
    reason: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: Dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    id: str
    summary: str
    evidence: List[Evidence]
    verdict: Optional[Verdict] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("evidence")
    @classmethod
    def validate_has_evidence(cls, v: List[Evidence]) -> List[Evidence]:
        if not v or len(v) == 0:
            raise ValueError("A Finding must contain at least one piece of Evidence.")
        return v
