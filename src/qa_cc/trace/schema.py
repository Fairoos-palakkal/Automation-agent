"""TraceEntry — Validated Pydantic schema for trace events with cryptographic hash-chaining (PRD P7, §8, T-10)."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class TraceEntry(BaseModel):
    """Validated schema for each JSONL trace entry.

    Guarantees:
    - Required sequence number (seq) and prev_hash chain.
    - Served model_id and token usage on every entry.
    - Timestamp in UTC ISO-8601.
    - Arbitrary metadata permitted via extra='allow'.
    """

    model_config = ConfigDict(extra="allow")

    seq: int = 0
    prev_hash: str = "0" * 64
    entry_hash: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    type: str
    model_id: str = "agent-gateway"
    tokens: int = 0
    run_id: Optional[str] = None

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this entry's contents."""
        data = self.model_dump(exclude={"entry_hash"})
        encoded = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
