"""Tests for Ground Truth Defect Freezing and Agent Isolation — Phase 0.7."""
import ast
import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestGroundTruthIsolation:
    def test_ground_truth_defects_frozen_and_partitioned(self):
        """Ground truth defects list must exist with >= 8 defects, 5 tuning and 3 held-out."""
        gt_file = REPO_ROOT / "benchmark" / "ground_truth" / "defects.json"
        assert gt_file.exists(), "defects.json does not exist"

        with open(gt_file, "r", encoding="utf-8") as f:
            defects = json.load(f)

        assert len(defects) >= 8, f"Expected at least 8 defects, found {len(defects)}"

        tuning = [d for d in defects if d.get("set") == "tuning"]
        held_out = [d for d in defects if d.get("set") == "held_out"]

        assert len(tuning) == 5, f"Expected 5 tuning defects, got {len(tuning)}"
        assert len(held_out) == 3, f"Expected 3 held-out defects, got {len(held_out)}"

        ids = [d["id"] for d in defects]
        assert len(ids) == len(set(ids)), "Defect IDs must be unique"

        for d in defects:
            assert "id" in d
            assert "category" in d
            assert "page" in d
            assert "matcher" in d
            assert isinstance(d["matcher"], dict)

    def test_own_site_pages_exist(self):
        """All pages referenced in defects.json must exist in benchmark/own_site/."""
        gt_file = REPO_ROOT / "benchmark" / "ground_truth" / "defects.json"
        with open(gt_file, "r", encoding="utf-8") as f:
            defects = json.load(f)

        own_site_dir = REPO_ROOT / "benchmark" / "own_site"
        assert own_site_dir.exists()

        for d in defects:
            page = d["page"].lstrip("/")
            page_path = own_site_dir / page
            assert page_path.exists(), f"Target page {page} for defect {d['id']} does not exist in benchmark/own_site/"

    def test_agent_and_llm_code_never_imports_or_references_ground_truth(self):
        """Static AST and lexical analysis: No agent or LLM module may reference benchmark/ground_truth."""
        src_dir = REPO_ROOT / "src" / "qa_cc"
        agent_and_llm_dirs = [src_dir / "agents", src_dir / "llm"]

        forbidden_patterns = ["ground_truth", "defects.json", "benchmark.ground_truth"]

        for check_dir in agent_and_llm_dirs:
            if not check_dir.exists():
                continue
            for py_file in check_dir.rglob("*.py"):
                code = py_file.read_text(encoding="utf-8")
                tree = ast.parse(code, filename=str(py_file))

                # Check import nodes
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            assert "ground_truth" not in alias.name, (
                                f"Forbidden import of ground_truth found in {py_file}: {alias.name}"
                            )
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        assert "ground_truth" not in module, (
                            f"Forbidden from-import of ground_truth found in {py_file}: {module}"
                        )
                    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                        for pattern in forbidden_patterns:
                            assert pattern not in node.value, (
                                f"Forbidden ground_truth string constant '{node.value}' found in {py_file}"
                            )
