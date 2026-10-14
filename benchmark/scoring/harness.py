"""ScoringHarness — Offline comparison of Findings against Planted Defects or Juice Shop scoreboard."""
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from qa_cc.verdict.evidence import Finding


class MismatchedModelError(Exception):
    """Raised when comparing runs evaluated with divergent benchmark model IDs."""
    pass


@dataclass
class ScoreReport:
    recall: float
    matched_defects: List[str]
    unmatched_findings: List[Finding]
    total_defects: int
    replay_rate: float = 0.0
    model_id: Optional[str] = None


class ScoringHarness:
    """Evaluates Run findings offline against frozen ground truth defects."""

    def __init__(self, ground_truth_path: Union[str, Path]):
        self.ground_truth_path = Path(ground_truth_path)

    def _load_defects(self) -> List[Dict[str, Any]]:
        with open(self.ground_truth_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def score(
        self,
        findings: List[Finding],
        include_held_out: bool = False,
        replay_results: Optional[Dict[str, bool]] = None,
        expected_model: Optional[str] = None,
        actual_model: Optional[str] = None,
    ) -> ScoreReport:
        if expected_model and actual_model and expected_model != actual_model:
            raise MismatchedModelError(
                f"Benchmark runs must use identical models. Expected '{expected_model}', found '{actual_model}'."
            )

        all_defects = self._load_defects()
        if include_held_out:
            target_defects = all_defects
        else:
            target_defects = [d for d in all_defects if d.get("set") == "tuning"]

        matched_defects: Set[str] = set()
        unmatched_findings: List[Finding] = []

        for finding in findings:
            found_match = False
            summary_lower = finding.summary.lower()
            finding_url = ""
            for ev in finding.evidence:
                if ev.metadata and "url" in ev.metadata:
                    finding_url = ev.metadata["url"]
                    break

            for defect in target_defects:
                defect_id = defect.get("id", "")
                keywords = [kw.lower() for kw in defect.get("keywords", []) if kw]
                page = defect.get("page", "")
                name = defect.get("name", "").strip()

                id_match = bool(defect_id and defect_id.lower() in summary_lower)
                kw_match = any(kw in summary_lower for kw in keywords) if keywords else False
                name_match = bool(name and name.lower() in summary_lower)

                desc = defect.get("description", "").lower()
                desc_words = [w for w in desc.split() if len(w) > 5]
                page_match = bool(page and (page in finding_url or page.lower() in summary_lower))
                desc_match = bool(page_match and any(w in summary_lower for w in desc_words))

                if id_match or kw_match or name_match or desc_match:
                    matched_defects.add(defect_id)
                    found_match = True

            if not found_match:
                unmatched_findings.append(finding)

        total_count = len(target_defects)
        recall = len(matched_defects) / total_count if total_count > 0 else 0.0

        replay_rate = 0.0
        if replay_results:
            successful_replays = sum(1 for passed in replay_results.values() if passed)
            replay_rate = successful_replays / len(replay_results)

        return ScoreReport(
            recall=recall,
            matched_defects=sorted(list(matched_defects)),
            unmatched_findings=unmatched_findings,
            total_defects=total_count,
            replay_rate=replay_rate,
            model_id=actual_model or expected_model,
        )
