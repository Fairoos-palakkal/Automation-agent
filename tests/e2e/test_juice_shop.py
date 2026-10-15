"""Tests for Juice Shop Integration — Phase 3.2 (Red -> Green).

Marked @pytest.mark.e2e.
Verification: pytest tests/e2e/test_juice_shop.py -v -m e2e
"""
import functools
import http.server
import json
from pathlib import Path
import socketserver
import threading
import pytest

from benchmark.scoring.harness import ScoringHarness
from benchmark.scoring.juice_shop import JuiceShopScoreboardReader
from qa_cc.gateway.gateway import ToolGateway
from qa_cc.verdict.evidence import Evidence, EvidenceType, Finding

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class MockJuiceShopHandler(http.server.BaseHTTPRequestHandler):
    """Mocks Juice Shop's challenge API."""

    def do_GET(self):
        if self.path.startswith("/api/Challenges"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = {
                "status": "success",
                "data": [
                    {
                        "id": 1,
                        "key": "errorHandlingChallenge",
                        "name": "Error Handling",
                        "category": "Security Misconfiguration",
                        "solved": True,
                    },
                    {
                        "id": 2,
                        "key": "scoreBoardChallenge",
                        "name": "Score Board",
                        "category": "Cryptographic Issues",
                        "solved": False,
                    },
                    {
                        "id": 3,
                        "key": "loginAdminChallenge",
                        "name": "Login Admin",
                        "category": "Injection",
                        "solved": True,
                    },
                ],
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Quiet logging during tests


@pytest.fixture(scope="module")
def juice_shop_server():
    """Starts a local mock Juice Shop server to provide deterministic scoreboard API."""
    with socketserver.TCPServer(("127.0.0.1", 0), MockJuiceShopHandler) as httpd:
        port = httpd.server_address[1]
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        yield f"http://127.0.0.1:{port}"
        httpd.shutdown()


@pytest.mark.e2e
class TestJuiceShopIntegration:
    def test_juice_shop_target_in_allowlist(self):
        """localhost:3000 is allowed by default in the target allowlist."""
        gateway = ToolGateway()
        assert gateway._is_url_allowed("http://localhost:3000") is True
        assert gateway._is_url_allowed("http://localhost:3000/#/search") is True
        assert gateway._is_url_allowed("http://localhost:3000/api/Challenges") is True
        assert gateway._is_url_allowed("http://127.0.0.1:3000") is True

    def test_scoreboard_reader_parses_challenges(self, juice_shop_server):
        """Reads Juice Shop's challenge API and returns the solved challenges list."""
        reader = JuiceShopScoreboardReader(base_url=juice_shop_server)
        challenges = reader.fetch_challenges()
        assert len(challenges) == 3

        solved = reader.get_solved_challenges(challenges)
        assert len(solved) == 2
        solved_names = [c["name"] for c in solved]
        assert "Error Handling" in solved_names
        assert "Login Admin" in solved_names
        assert "Score Board" not in solved_names

    def test_scoring_harness_uses_scoreboard(self):
        """For Juice Shop target, scoring uses scoreboard solved challenges instead of matchers."""
        scoreboard_challenges = [
            {"id": 1, "name": "Error Handling", "solved": True},
            {"id": 2, "name": "Score Board", "solved": False},
            {"id": 3, "name": "Login Admin", "solved": True},
            {"id": 4, "name": "Password Strength", "solved": False},
        ]
        finding = Finding(
            id="F-JS-1",
            summary="Discovered unhandled error handling stack trace",
            evidence=[Evidence(type=EvidenceType.DOM_SNAPSHOT, content="Error 500")],
        )

        harness = ScoringHarness(ground_truth_path=REPO_ROOT / "benchmark" / "ground_truth" / "defects.json")
        report = harness.score(
            findings=[finding],
            target_type="juice_shop",
            scoreboard_challenges=scoreboard_challenges,
        )

        # 2 out of 4 challenges solved in scoreboard -> 50% recall
        assert report.total_defects == 4
        assert report.recall == 0.5
        assert "Error Handling" in report.matched_defects
        assert "Login Admin" in report.matched_defects
        assert len(report.matched_defects) == 2
