"""Tests for Own Site FastAPI Mock Backend — Phase 2.6 (Red → Green)."""
import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from qa_cc.tools.mock_api import app, PLANTED_API_DEFECTS


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestMockApiBackend:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_mock_api_serves_endpoints(self, client):
        """GET /api/health and other endpoints return valid HTTP responses."""
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

        cart_res = client.get("/api/cart")
        assert cart_res.status_code == 200
        assert "items" in cart_res.json()

    def test_mock_api_has_planted_defects(self, client):
        """Specific requests trigger planted API defects (DEFECT-001, DEFECT-004, DEFECT-007)."""
        # DEFECT-001: Missing email validation (accepts invalid email string without 400/422)
        res1 = client.post("/api/contact", json={"name": "Alice", "email": "notanemail", "message": "hello"})
        assert res1.status_code == 200
        assert res1.json()["success"] is True

        # DEFECT-004: Cart allows negative quantity and produces negative total
        res2 = client.post("/api/cart/update", json={"item_id": "widget-1", "quantity": -3})
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["quantity"] == -3
        assert data2["total"] < 0

        # DEFECT-007: Repeated promo application causes negative balance
        res3a = client.post("/api/cart/apply-promo", json={"code": "SAVE20", "total": 15.0})
        assert res3a.status_code == 200
        assert res3a.json()["new_total"] == -5.0  # Discount exceeds total, balance goes negative

    def test_mock_api_defects_in_ground_truth(self):
        """All planted API defect IDs exist in ground truth defects.json."""
        gt_path = REPO_ROOT / "benchmark" / "ground_truth" / "defects.json"
        assert gt_path.exists()

        with open(gt_path, "r", encoding="utf-8") as f:
            gt_defects = json.load(f)

        gt_ids = {d["id"] for d in gt_defects}
        assert len(PLANTED_API_DEFECTS) >= 2

        for defect_id in PLANTED_API_DEFECTS:
            assert defect_id in gt_ids, f"Planted API defect {defect_id} not found in defects.json"
