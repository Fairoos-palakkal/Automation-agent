"""Playwright driver adapter wrapping Playwright Page for BrowserTools."""
from typing import Any, Dict, List


class PlaywrightPageDriver:
    """Adapts a Playwright Page instance to the BrowserTools driver interface."""

    def __init__(self, page: Any):
        self._page = page
        self.console_messages: List[Dict[str, Any]] = []
        self._page.on(
            "console",
            lambda msg: self.console_messages.append({"type": msg.type, "text": msg.text}),
        )

    def goto(self, url: str) -> Any:
        return self._page.goto(url)

    def click(self, selector: str, timeout: float = 5000) -> Any:
        return self._page.click(selector, timeout=timeout)

    def fill(self, selector: str, value: str, timeout: float = 5000) -> Any:
        return self._page.fill(selector, value, timeout=timeout)

    def screenshot(self, path: str) -> str:
        self._page.screenshot(path=path)
        return path

    def content(self) -> str:
        return self._page.content()

    @property
    def url(self) -> str:
        return self._page.url
