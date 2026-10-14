"""Browser tools — navigate, click, fill, screenshot, console capture, and snapshot compaction."""
import re
from typing import Any, Dict, List, Optional

from qa_cc.verdict.evidence import Evidence, EvidenceType


def compact_snapshot(html: str, max_chars: int = 4000) -> str:
    """Compact raw HTML into a clean, token-efficient representation for agent consumption."""
    # Strip script tags
    cleaned = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    # Strip style tags
    cleaned = re.sub(r"<style[\s\S]*?</style>", "", cleaned, flags=re.IGNORECASE)
    # Strip comments
    cleaned = re.sub(r"<!--[\s\S]*?-->", "", cleaned)
    # Normalize multiple whitespace characters
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]

    return cleaned


class BrowserTools:
    """Encapsulates browser automation commands operating on a driver."""

    def __init__(self, driver: Any):
        self.driver = driver

    def navigate(self, url: str) -> Dict[str, Any]:
        self.driver.goto(url)
        content = self.driver.content()
        return {
            "url": getattr(self.driver, "url", url),
            "snapshot": compact_snapshot(content),
        }

    def click(self, selector: str) -> Dict[str, Any]:
        self.driver.click(selector)
        content = self.driver.content()
        return {
            "url": getattr(self.driver, "url", ""),
            "snapshot": compact_snapshot(content),
        }

    def fill(self, selector: str, value: str) -> Dict[str, Any]:
        self.driver.fill(selector, value)
        content = self.driver.content()
        return {
            "snapshot": compact_snapshot(content),
        }

    def screenshot(self, path: str = "artifacts/screenshot.png") -> Evidence:
        saved_path = self.driver.screenshot(path)
        return Evidence(
            type=EvidenceType.SCREENSHOT,
            content=str(saved_path or path),
        )

    def console_errors(self) -> List[Dict[str, Any]]:
        messages = getattr(self.driver, "console_messages", [])
        return [m for m in messages if m.get("type") == "error"]

    def snapshot(self) -> str:
        return compact_snapshot(self.driver.content())
