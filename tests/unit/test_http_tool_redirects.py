"""Unit tests for T-03: HTTP Redirects and Body Size Cap (Red Phase)."""
import pytest
from qa_cc.gateway.gateway import TargetNotAllowed
from qa_cc.tools.http import HttpTool


class DummyResponse:
    def __init__(self, status_code: int, text: str = "", headers: dict = None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


def test_redirect_to_disallowed_host_raises_target_not_allowed():
    """302 redirect from an allowed host to a disallowed host raises TargetNotAllowed."""
    calls = []

    def mock_requester(method, url, headers, body):
        calls.append(url)
        if url == "http://localhost:3000/redirect":
            return DummyResponse(
                status_code=302,
                text="Redirecting",
                headers={"Location": "https://evil.com/leak"},
            )
        return DummyResponse(status_code=200, text="OK")

    tool = HttpTool(requester=mock_requester, allowlist=["localhost", "127.0.0.1"])

    with pytest.raises(TargetNotAllowed) as exc_info:
        tool.request("GET", "http://localhost:3000/redirect")

    assert "evil.com" in str(exc_info.value) or "not permitted" in str(exc_info.value).lower()
    assert len(calls) == 1


def test_redirect_to_allowed_host_is_followed():
    """302 redirect from an allowed host to another allowed host succeeds within hop limit."""
    calls = []

    def mock_requester(method, url, headers, body):
        calls.append(url)
        if url == "http://localhost:3000/first":
            return DummyResponse(
                status_code=302,
                text="Redirecting to second",
                headers={"Location": "http://127.0.0.1:3000/second"},
            )
        if url == "http://127.0.0.1:3000/second":
            return DummyResponse(
                status_code=302,
                text="Redirecting to target",
                headers={"Location": "/final"},
            )
        if url == "http://127.0.0.1:3000/final":
            return DummyResponse(status_code=200, text="Final Destination")
        return DummyResponse(status_code=404, text="Not Found")

    tool = HttpTool(requester=mock_requester, allowlist=["localhost", "127.0.0.1"])
    res = tool.request("GET", "http://localhost:3000/first")

    assert res["status_code"] == 200
    assert res["body"] == "Final Destination"
    assert len(calls) == 3


def test_exceeding_max_redirects_raises():
    """Chained redirects exceeding max_redirects (5 hops) raise an error."""
    def infinite_redirect(method, url, headers, body):
        return DummyResponse(
            status_code=302,
            text="Redirect loop",
            headers={"Location": "http://localhost:3000/loop"},
        )

    tool = HttpTool(requester=infinite_redirect, allowlist=["localhost"], max_redirects=5)
    with pytest.raises(Exception) as exc_info:
        tool.request("GET", "http://localhost:3000/loop")

    assert "redirect" in str(exc_info.value).lower()


def test_response_body_cap_exceeding_256kb():
    """HTTP response bodies exceeding 256 KB are capped."""
    huge_text = "A" * (300 * 1024)  # 300 KB

    def mock_requester(method, url, headers, body):
        return DummyResponse(status_code=200, text=huge_text)

    tool = HttpTool(requester=mock_requester, allowlist=["localhost"], max_body_bytes=256 * 1024)
    res = tool.request("GET", "http://localhost:3000/huge")

    # Body must be capped to at most 256 KB (or truncated indicator attached)
    assert len(res["body"].encode("utf-8")) <= (256 * 1024) + 100
    assert "[TRUNCATED" in res["body"] or len(res["body"]) <= 256 * 1024
