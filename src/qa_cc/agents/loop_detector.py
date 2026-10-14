"""Loop detection and recovery state machine for agent action loops.

Fingerprints actions and observations. If an agent repeats identical action-observation
pairs 3 times, triggers deterministic recovery (re-observe -> try alternate -> terminate inconclusive).
"""
from enum import Enum
import hashlib
import json
from typing import Any, Dict, Optional, Tuple


class RecoveryAction(str, Enum):
    CONTINUE = "CONTINUE"
    TRIGGER_RECOVERY = "TRIGGER_RECOVERY"
    RE_OBSERVE = "RE_OBSERVE"
    TRY_ALTERNATE = "TRY_ALTERNATE"
    TERMINATE_INCONCLUSIVE = "TERMINATE_INCONCLUSIVE"


def compute_action_fingerprint(tool: str, args: Dict[str, Any], url: str = "") -> str:
    """Deterministic hash of tool name, normalized arguments, and target URL."""
    norm_args = json.dumps(args, sort_keys=True, default=str)
    raw = f"{tool}|{norm_args}|{url}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_observation_fingerprint(dom_or_state: str) -> str:
    """Deterministic hash of normalized DOM/page state observation."""
    norm = "".join(dom_or_state.split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


class LoopDetector:
    """Detects cycles in action-observation history and guides recovery."""

    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.last_pair: Optional[Tuple[str, str]] = None
        self.consecutive_count: int = 0

    def check(self, action_fp: str, observation_fp: str) -> RecoveryAction:
        current_pair = (action_fp, observation_fp)

        if current_pair == self.last_pair:
            self.consecutive_count += 1
        else:
            self.last_pair = current_pair
            self.consecutive_count = 1

        if self.consecutive_count < self.threshold:
            return RecoveryAction.CONTINUE

        excess = self.consecutive_count - self.threshold
        if excess == 0:
            return RecoveryAction.RE_OBSERVE
        elif excess == 1:
            return RecoveryAction.TRY_ALTERNATE
        else:
            return RecoveryAction.TERMINATE_INCONCLUSIVE

    def reset(self) -> None:
        self.last_pair = None
        self.consecutive_count = 0
