"""Target Profile definition and loading (ADR-0002, F-07).

A Target Profile declares target-specific metadata and scope hints,
recorded in the trace and supplied identically to baseline and multi-agent
configurations to preserve black-box prompt purity.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TargetProfile(BaseModel):
    """Target-specific metadata and scope hints."""

    name: str = ""
    description: str = ""
    hints: List[str] = Field(default_factory=list)
    endpoints: List[str] = Field(default_factory=list)
    selectors: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "TargetProfile":
        """Load target profile from a JSON file."""
        file_path = Path(path)
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to serializable dictionary."""
        return self.model_dump()

    def format_for_prompt(self) -> str:
        """Format target profile contents for inclusion in agent context."""
        parts: List[str] = []
        if self.name:
            parts.append(f"Target: {self.name}")
        if self.description:
            parts.append(f"Description: {self.description}")
        if self.endpoints:
            parts.append("Known Endpoints:\n" + "\n".join(f"- {ep}" for ep in self.endpoints))
        if self.selectors:
            parts.append("Scope Elements:\n" + "\n".join(f"- {sel}" for sel in self.selectors))
        if self.hints:
            parts.append("Scope Hints:\n" + "\n".join(f"- {h}" for h in self.hints))
        return "\n\n".join(parts)
