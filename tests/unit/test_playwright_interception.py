"""Unit tests for Playwright route interception (T-03 Red Phase)."""
from unittest.mock import MagicMock
import pytest
from qa_cc.tools.playwright_driver import PlaywrightPageDriver
from qa_cc.trace.writer import TraceWriter


class MockRequest:
    def __init__(self, url: str):
        self.url = url


class MockRoute:
    def __init__(self, url: str):
        self.request = MockRequest(url)
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


class MockPage:
    def __init__(self):
        self._handlers = {}
        self.url = "http://localhost:3000"

    def on(self, event, handler):
        pass

    def route(self, pattern, handler):
        self._handlers[pattern] = handler


def test_playwright_interception_aborts_non_allowlisted_request(tmp_path):
    """External/disallowed network requests in browser sessions are aborted and traced as denials."""
    mock_page = MockPage()
    trace_writer = TraceWriter(path=tmp_path / "trace.jsonl")
    driver = PlaywrightPageDriver(
        mock_page,
        allowlist=["localhost", "127.0.0.1"],
        trace_writer=trace_writer,
    )

    assert "**/*" in mock_page._handlers
    route_handler = mock_page._handlers["**/*"]

    # 1. Allowed request
    allowed_route = MockRoute("http://localhost:3000/main.js")
    route_handler(allowed_route)
    assert allowed_route.continued is True
    assert allowed_route.aborted is False

    # 2. Disallowed request (e.g. external link click / tracking beacon)
    disallowed_route = MockRoute("https://evil-tracking.com/beacon")
    route_handler(disallowed_route)
    assert disallowed_route.aborted is True
    assert disallowed_route.continued is False
    assert "https://evil-tracking.com/beacon" in driver.denied_requests

    # Verify traced denial
    entries = trace_writer.read_entries()
    denial_entries = [e for e in entries if e.get("type") == "tool_call" and e.get("tool_name") == "browser_network_denial"]
    assert len(denial_entries) == 1
    assert denial_entries[0]["args"]["url"] == "https://evil-tracking.com/beacon"
