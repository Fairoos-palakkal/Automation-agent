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


from qa_cc.security.scrubber import Scrubber
from qa_cc.trace.schema import TraceEntry


class TraceWriter:
    """Writes trace entries to a JSONL file with cryptographic hash chaining and secret scrubbing.

    Args:
        path: Destination file path. Parent directories are created if absent.
        secret_env_vars: Names of environment variables whose values should be
                         scrubbed from all trace output.
        scrubber: Optional pre-configured Scrubber instance.
        run_id: Optional unique identifier for this Run.
    """

    SCRUB_PLACEHOLDER = "[SCRUBBED]"

    def __init__(
        self,
        path: Path | str,
        secret_env_vars: list[str] | None = None,
        scrubber: Scrubber | None = None,
        run_id: str | None = None,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.scrubber = scrubber or Scrubber(secret_env_vars=secret_env_vars)
        self.run_id = run_id
        self._secret_values: set[str] = set()
        for var in secret_env_vars or []:
            value = os.environ.get(var)
            if value:
                self._secret_values.add(value)
                self.scrubber.add_secret(value)

        self._seq = 0
        self._prev_hash = "0" * 64
        if self._path.exists() and self._path.stat().st_size > 0:
            existing = self.read_entries()
            if existing:
                last = existing[-1]
                self._seq = last.get("seq", len(existing) - 1) + 1
                self._prev_hash = last.get("entry_hash", "0" * 64)

    def record(self, entry: dict[str, Any] | TraceEntry) -> TraceEntry:
        """Append one entry to the JSONL trace file.

        Validates against TraceEntry schema, computes SHA-256 hash-chain,
        and scrubs secrets recursively.
        """
        if isinstance(entry, TraceEntry):
            raw = entry.model_dump()
        else:
            raw = dict(entry)

        seq = raw.get("seq", self._seq)
        prev_hash = raw.get("prev_hash", self._prev_hash)
        timestamp = raw.get("timestamp", self._now_iso())
        model_id = raw.get("model_id", "agent-gateway")
        tokens = raw.get("tokens", 0)
        run_id = raw.get("run_id", self.run_id)

        entry_dict = {
            **raw,
            "seq": seq,
            "prev_hash": prev_hash,
            "timestamp": timestamp,
            "model_id": model_id,
            "tokens": tokens,
        }
        if run_id is not None:
            entry_dict["run_id"] = run_id

        scrubbed = self._scrub(entry_dict)
        trace_obj = TraceEntry(**scrubbed)
        if not trace_obj.entry_hash:
            trace_obj.entry_hash = trace_obj.compute_hash()

        self._seq = trace_obj.seq + 1
        self._prev_hash = trace_obj.entry_hash

        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(trace_obj.model_dump(), default=str) + "\n")

        return trace_obj

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
        return self.scrubber.scrub(obj)
