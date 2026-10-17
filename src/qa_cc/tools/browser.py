"""Browser tools — navigate, click, fill, screenshot, console capture, and snapshot compaction."""
import re
from typing import Any, Dict, List, Optional

from qa_cc.verdict.evidence import Evidence, EvidenceType


def compact_snapshot(html: str, max_chars: int = 25000) -> str:
    """Compact raw HTML into a clean, token-efficient representation for agent consumption."""
    # Strip head tags (meta, links, preconnects, stylesheets)
    cleaned = re.sub(r"<head[\s\S]*?</head>", "", html, flags=re.IGNORECASE)
    # Strip script tags
    cleaned = re.sub(r"<script[\s\S]*?</script>", "", cleaned, flags=re.IGNORECASE)
    # Strip style tags
    cleaned = re.sub(r"<style[\s\S]*?</style>", "", cleaned, flags=re.IGNORECASE)
    # Strip svg tags
    cleaned = re.sub(r"<svg[\s\S]*?</svg>", "", cleaned, flags=re.IGNORECASE)
    # Strip comments
    cleaned = re.sub(r"<!--[\s\S]*?-->", "", cleaned)
    # Strip framework / noise attributes (Angular internals, ripples, empty attrs)
    cleaned = re.sub(r"(_ngcontent|_nghost)[^= \"\x27>]*(=[\"\x27][^\"]*[\"\x27])?", "", cleaned)
    cleaned = re.sub(r"mat-ripple-loader-[^= \"\x27>]*(=[\"\x27][^\"]*[\"\x27])?", "", cleaned)
    cleaned = re.sub(r"aria-hidden=\"true\"", "", cleaned)
    cleaned = re.sub(r"style=\"\"", "", cleaned)
    # Normalize multiple whitespace characters
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]

    return cleaned


from qa_cc.security.fence import ContentFence, delimit_dom_content


class BrowserTools:
    """Encapsulates browser automation commands operating on a driver."""

    def __init__(self, driver: Any, delimit: bool = True, fence: Optional[ContentFence] = None):
        self.driver = driver
        self.delimit = delimit
        self.fence = fence or ContentFence()

    def _format_snapshot(self, content: str) -> str:
        compacted = compact_snapshot(content)
        if self.delimit:
            return self.fence.wrap(compacted)
        return compacted

    def navigate(self, url: str) -> Dict[str, Any]:
        self.driver.goto(url)
        content = self.driver.content()
        return {
            "url": getattr(self.driver, "url", url),
            "snapshot": self._format_snapshot(content),
        }

    def click(self, selector: str) -> Dict[str, Any]:
        self.driver.click(selector)
        content = self.driver.content()
        return {
            "url": getattr(self.driver, "url", ""),
            "snapshot": self._format_snapshot(content),
        }

    def fill(self, selector: str, value: str) -> Dict[str, Any]:
        self.driver.fill(selector, value)
        content = self.driver.content()
        return {
            "snapshot": self._format_snapshot(content),
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
        return self._format_snapshot(self.driver.content())
