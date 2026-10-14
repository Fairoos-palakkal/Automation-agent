"""Tests for Browser Tools — Phase 1.2 (Red -> Green)."""
import pytest
from unittest.mock import MagicMock

from qa_cc.tools.browser import (
    BrowserTools,
    compact_snapshot,
)
from qa_cc.verdict.evidence import EvidenceType


class FakePageDriver:
    """Deterministic in-memory driver simulating browser page interactions for unit tests."""
    def __init__(self):
        self.url = "about:blank"
        self.html = "<html><body><h1>Acme Home</h1><button id='btn'>Click</button><input id='name' value=''/></body></html>"
        self.console_messages = []
        self.screenshots = []

    def goto(self, url: str):
        self.url = url
        if "catalog" in url:
            self.html = "<html><body><h1>Catalog</h1><button id='filter-btn'>Filter</button></body></html>"
        else:
            self.html = f"<html><body><h1>Page: {url}</h1><button id='btn'>Click</button></body></html>"
        return {"url": self.url, "title": "Page Title"}

    def click(self, selector: str):
        if selector == "#filter-btn":
            self.console_messages.append({"type": "error", "text": "TypeError: Cannot read properties of undefined"})
            self.html = "<html><body><h1>Catalog</h1><div id='err'>Error occurred</div></body></html>"
        else:
            self.html = f"<html><body><h1>Clicked {selector}</h1></body></html>"

    def fill(self, selector: str, value: str):
        self.html = f"<html><body><input id='name' value='{value}'/></body></html>"

    def screenshot(self, path: str = "artifacts/screenshot.png"):
        self.screenshots.append(path)
        return path

    def content(self):
        return self.html


class TestBrowserTools:
    def test_navigate_returns_page_snapshot(self):
        """navigate(url) loads page and returns a compacted snapshot."""
        driver = FakePageDriver()
        tools = BrowserTools(driver=driver)

        result = tools.navigate("http://localhost:3000/catalog.html")
        assert result["url"] == "http://localhost:3000/catalog.html"
        assert "snapshot" in result
        assert "Catalog" in result["snapshot"]

    def test_click_returns_updated_snapshot(self):
        """click(selector) triggers interaction and returns the updated snapshot."""
        driver = FakePageDriver()
        tools = BrowserTools(driver=driver)
        tools.navigate("http://localhost:3000/catalog.html")

        result = tools.click("#filter-btn")
        assert "Error occurred" in result["snapshot"]

    def test_fill_sets_value(self):
        """fill(selector, value) updates the form field."""
        driver = FakePageDriver()
        tools = BrowserTools(driver=driver)

        result = tools.fill("#name", "Jane Doe")
        assert "Jane Doe" in result["snapshot"]

    def test_screenshot_returns_evidence(self):
        """screenshot() produces an Evidence record of type screenshot."""
        driver = FakePageDriver()
        tools = BrowserTools(driver=driver)

        evidence = tools.screenshot("artifacts/test.png")
        assert evidence.type == EvidenceType.SCREENSHOT
        assert evidence.content == "artifacts/test.png"

    def test_console_capture_returns_errors(self):
        """console_errors() returns list of captured error messages."""
        driver = FakePageDriver()
        tools = BrowserTools(driver=driver)
        tools.navigate("http://localhost:3000/catalog.html")
        tools.click("#filter-btn")

        errors = tools.console_errors()
        assert len(errors) == 1
        assert "TypeError" in errors[0]["text"]

    def test_snapshot_is_compacted(self):
        """compact_snapshot strips noisy tags, scripts, and truncates beyond length cap."""
        raw_html = """
        <html>
            <head><script>console.log("noisy inline script");</script><style>.box { color: red; }</style></head>
            <body>
                <!-- HTML Comment -->
                <div>
                    <h1>Header</h1>
                    <p>Some text</p>
                </div>
            </body>
        </html>
        """
        compacted = compact_snapshot(raw_html, max_chars=100)
        assert "<script>" not in compacted
        assert "<style>" not in compacted
        assert "<!--" not in compacted
        assert len(compacted) <= 100
