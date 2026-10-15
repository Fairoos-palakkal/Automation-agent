"""Juice Shop Scoreboard Reader — reads challenge states from OWASP Juice Shop API (Phase 3.2)."""
import json
from typing import Any, Dict, List, Optional
import urllib.request


class JuiceShopScoreboardReader:
    """Reads and parses solved challenges from OWASP Juice Shop /api/Challenges."""

    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url.rstrip("/")

    def fetch_challenges(self, url: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch challenges list from /api/Challenges endpoint."""
        endpoint = url or f"{self.base_url}/api/Challenges"
        try:
            req = urllib.request.Request(
                endpoint,
                headers={"Accept": "application/json", "User-Agent": "qa_cc/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "data" in data:
                    return data["data"]
                elif isinstance(data, list):
                    return data
                return []
        except Exception:
            return []

    def get_solved_challenges(self, challenges: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Extract all challenges marked solved: True."""
        if challenges is None:
            challenges = self.fetch_challenges()
        return [c for c in challenges if isinstance(c, dict) and c.get("solved") is True]
