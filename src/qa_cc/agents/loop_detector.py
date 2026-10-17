"""Loop detection and recovery state machine for agent action loops.

Fingerprints actions and observations. If an agent repeats identical action-observation
pairs 3 times, triggers deterministic recovery (re-observe -> try alternate -> terminate inconclusive).
"""
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple


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
    """Detects cycles in action-observation history (periods 1, 2, 3) and guides recovery."""

    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.history: List[Tuple[str, str]] = []
        self.active_pattern: Optional[Tuple[Tuple[str, str], ...]] = None
        self.active_cycle_count: int = 0
        # Backward compatibility attributes
        self.last_pair: Optional[Tuple[str, str]] = None
        self.consecutive_count: int = 0

    def check(self, action_fp: str, observation_fp: str) -> RecoveryAction:
        current_pair = (action_fp, observation_fp)
        self.history.append(current_pair)

        # Update backward-compatibility consecutive count for single repeats
        if current_pair == self.last_pair:
            self.consecutive_count += 1
        else:
            self.last_pair = current_pair
            self.consecutive_count = 1

        # 1. If an active multi-element pattern is already tracked, check progression
        if self.active_pattern is not None:
            p_len = len(self.active_pattern)
            # Check if this step is still consistent with the active pattern
            step_in_pattern = (len(self.history) - 1) % p_len
            expected_pair = self.active_pattern[step_in_pattern]
            if current_pair == expected_pair:
                # If a full cycle just finished
                if step_in_pattern == p_len - 1:
                    self.active_cycle_count += 1
                    if self.active_cycle_count == 2:
                        return RecoveryAction.RE_OBSERVE
                    elif self.active_cycle_count == 3:
                        return RecoveryAction.TRY_ALTERNATE
                    else:
                        return RecoveryAction.TERMINATE_INCONCLUSIVE
                return RecoveryAction.CONTINUE
            else:
                # Pattern broken
                self.active_pattern = None
                self.active_cycle_count = 0

        # 2. Check for Period 1 (A, A, A...)
        c1 = 0
        for item in reversed(self.history):
            if item == current_pair:
                c1 += 1
            else:
                break
        if c1 >= self.threshold:
            excess = c1 - self.threshold
            if excess == 0:
                return RecoveryAction.RE_OBSERVE
            elif excess == 1:
                return RecoveryAction.TRY_ALTERNATE
            else:
                return RecoveryAction.TERMINATE_INCONCLUSIVE

        # 3. Check for Period 2 (A, B, A, B...)
        if len(self.history) >= 4:
            p2 = (self.history[-2], self.history[-1])
            if p2[0] != p2[1]:
                prev_p2 = (self.history[-4], self.history[-3])
                if p2 == prev_p2:
                    self.active_pattern = p2
                    self.active_cycle_count = 2
                    return RecoveryAction.RE_OBSERVE

        # 4. Check for Period 3 (A, B, C, A, B, C...)
        if len(self.history) >= 6:
            p3 = (self.history[-3], self.history[-2], self.history[-1])
            if not (p3[0] == p3[1] == p3[2]):
                prev_p3 = (self.history[-6], self.history[-5], self.history[-4])
                if p3 == prev_p3:
                    self.active_pattern = p3
                    self.active_cycle_count = 2
                    return RecoveryAction.RE_OBSERVE

        return RecoveryAction.CONTINUE

    def reset(self) -> None:
        self.history.clear()
        self.active_pattern = None
        self.active_cycle_count = 0
        self.last_pair = None
        self.consecutive_count = 0

