"""TraceWriter — append-mode JSONL trace writer with secret scrubbing.

Every model call, tool call, and system event is written as a single JSON line.
Secrets (env var values) are scrubbed to [SCRUBBED] before writing.

Rule: Secrets come from environment variables only. Scrub them from traces.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceWriter:
    """Writes trace entries to a JSONL file.

    Args:
        path: Destination file path. Parent directories are created if absent.
        secret_env_vars: Names of environment variables whose values should be
                         scrubbed from all trace output.
    """

    SCRUB_PLACEHOLDER = "[SCRUBBED]"

    def __init__(
        self,
        path: Path | str,
        secret_env_vars: list[str] | None = None,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._secret_values: set[str] = set()
        for var in secret_env_vars or []:
            value = os.environ.get(var)
            if value:
                self._secret_values.add(value)

    def record(self, entry: dict[str, Any]) -> None:
        """Append one entry to the JSONL trace file.

        Args:
            entry: A dict with at minimum ``type``, ``model_id``, and ``tokens`` keys.
                   A ``timestamp`` field is injected automatically if absent.
        """
        stamped = {"timestamp": self._now_iso(), **entry}
        scrubbed = self._scrub(stamped)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(scrubbed) + "\n")

    def record_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
        model_id: str = "agent-gateway",
        tokens: int = 0,
    ) -> None:
        """Convenience method to record a tool call entry."""
        self.record({
            "type": "tool_call",
            "tool_name": tool_name,
            "args": args,
            "result": result,
            "model_id": model_id,
            "tokens": tokens,
        })

    def read_entries(self) -> list[dict[str, Any]]:
        """Read and parse all JSONL entries from the trace file."""
        if not self._path.exists():
            return []
        entries = []
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(tz=timezone.utc).isoformat()

    def _scrub(self, obj: Any) -> Any:
        """Recursively replace secret values with the scrub placeholder."""
        if not self._secret_values:
            return obj
        if isinstance(obj, str):
            result = obj
            for secret in self._secret_values:
                result = result.replace(secret, self.SCRUB_PLACEHOLDER)
            return result
        if isinstance(obj, dict):
            return {k: self._scrub(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._scrub(item) for item in obj]
        return obj
