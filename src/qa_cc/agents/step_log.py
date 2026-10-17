"""StepLog — Append-only per-run sequence of executable actions and observations.

Used for defect reproduction, replay, and linking Findings to concrete steps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class StepEntry:
    """An individual recorded tool action and observation in the StepLog."""

    step_id: str
    tool: str
    args: Dict[str, Any]
    url_before: str = ""
    url_after: str = ""
    ok: bool = True
    error: Optional[str] = None
    result: Any = None
    evidence_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "step_id": self.step_id,
            "tool": self.tool,
            "args": self.args,
            "url_before": self.url_before,
            "url_after": self.url_after,
            "ok": self.ok,
            "timestamp": self.timestamp,
        }
        if self.error is not None:
            data["error"] = self.error
        if self.evidence_id is not None:
            data["evidence_id"] = self.evidence_id
        if self.result is not None:
            data["result"] = self.result
        return data


class StepLog:
    """Append-only sequence of executed actions and observations for one Run/Task."""

    def __init__(self) -> None:
        self._steps: List[StepEntry] = []
        self._last_observation: Any = None
        self._last_observation_type: Optional[str] = None

    def record_step(
        self,
        tool: str,
        args: Dict[str, Any],
        url_before: str = "",
        url_after: str = "",
        ok: bool = True,
        error: Optional[str] = None,
        result: Any = None,
        evidence_id: Optional[str] = None,
    ) -> StepEntry:
        """Record an executed step and update last observation cache."""
        step_id = f"step-{len(self._steps) + 1}"
        entry = StepEntry(
            step_id=step_id,
            tool=tool,
            args=args,
            url_before=url_before,
            url_after=url_after,
            ok=ok,
            error=error,
            result=result,
            evidence_id=evidence_id,
        )
        self._steps.append(entry)

        if ok and result is not None:
            self._last_observation = result
            if isinstance(result, dict):
                if "snapshot" in result:
                    self._last_observation_type = "dom_snapshot"
                elif "errors" in result or "console_errors" in result:
                    self._last_observation_type = "console_log"
                elif "status_code" in result:
                    self._last_observation_type = "network_request"
            elif isinstance(result, str):
                self._last_observation_type = "dom_snapshot"

        return entry

    @property
    def steps(self) -> List[StepEntry]:
        return list(self._steps)

    @property
    def last_observation(self) -> Any:
        return self._last_observation

    @property
    def last_observation_type(self) -> Optional[str]:
        return self._last_observation_type

    def get_step_dicts(self) -> List[Dict[str, Any]]:
        return [step.to_dict() for step in self._steps]

    def get_steps_by_ids(self, step_ids: List[str]) -> List[StepEntry]:
        id_set = set(step_ids)
        return [step for step in self._steps if step.step_id in id_set]

    def capture_evidence(self, url: str = "", requested_type: Optional[str] = None) -> Optional[Any]:
        """Build Evidence from the last real observation, ignoring fabricated model text.

        If requested_type is specified (e.g. 'console_log', 'network_request', 'dom_snapshot'):
        - Returns real observation evidence if compatible.
        - Returns None if incompatible (e.g. 'console_log' requested but only 'dom_snapshot'
          was captured with no console errors), allowing caller to handle fallback.
        """
        if self._last_observation is None:
            return None

        import json
        from qa_cc.verdict.evidence import Evidence, EvidenceType

        if requested_type is not None:
            req = str(requested_type).lower()
            if req == "console_log":
                if self._last_observation_type != "console_log" and not (
                    isinstance(self._last_observation, dict) and ("errors" in self._last_observation or "console_errors" in self._last_observation)
                ):
                    return None
            elif req == "network_request":
                if self._last_observation_type != "network_request" and not (
                    isinstance(self._last_observation, dict) and "status_code" in self._last_observation
                ):
                    return None
            elif req in ("dom_snapshot", "screenshot"):
                if self._last_observation_type not in ("dom_snapshot", "screenshot"):
                    return None

        if self._last_observation_type == "network_request" or (
            isinstance(self._last_observation, dict) and "status_code" in self._last_observation
        ):
            content = json.dumps(self._last_observation.get("body", self._last_observation), default=str)
            return Evidence(
                type=EvidenceType.NETWORK_REQUEST,
                content=content,
                metadata={"url": url, "status_code": self._last_observation.get("status_code", 200)},
            )
        elif self._last_observation_type == "console_log" or (
            isinstance(self._last_observation, dict) and ("errors" in self._last_observation or "console_errors" in self._last_observation)
        ):
            errors = self._last_observation.get("errors") or self._last_observation.get("console_errors", [])
            content = json.dumps(errors, default=str) if isinstance(errors, (list, dict)) else str(errors)
            return Evidence(
                type=EvidenceType.CONSOLE_LOG,
                content=content,
                metadata={"url": url},
            )
        elif isinstance(self._last_observation, dict) and "snapshot" in self._last_observation:
            return Evidence(
                type=EvidenceType.DOM_SNAPSHOT,
                content=str(self._last_observation["snapshot"]),
                metadata={"url": url},
            )
        elif isinstance(self._last_observation, dict) and "path" in self._last_observation:
            return Evidence(
                type=EvidenceType.SCREENSHOT,
                content=str(self._last_observation["path"]),
                metadata={"url": url},
            )
        elif isinstance(self._last_observation, str):
            return Evidence(
                type=EvidenceType.DOM_SNAPSHOT,
                content=self._last_observation,
                metadata={"url": url},
            )
        return None

    def __len__(self) -> int:
        return len(self._steps)

