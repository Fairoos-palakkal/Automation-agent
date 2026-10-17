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

    def _get_errors_and_failures(self) -> Dict[str, Any]:
        obs: Dict[str, Any] = {}
        messages = getattr(self.driver, "console_messages", [])
        errors = [m.get("text", "") for m in messages if m.get("type") == "error"]
        failed_requests = list(getattr(self.driver, "failed_requests", []))
        if errors:
            fenced_errors = self.fence.wrap("\n".join(errors[:5])) if self.delimit else "\n".join(errors[:5])
            obs["console_errors"] = fenced_errors
        if failed_requests:
            req_lines = [
                f"{r.get('method', 'GET')} {r.get('url', '')} -> {r.get('status', r.get('failure', 'failed'))}"
                for r in failed_requests[:5]
            ]
            fenced_failed = self.fence.wrap("\n".join(req_lines)) if self.delimit else "\n".join(req_lines)
            obs["failed_requests"] = fenced_failed
        return obs

    def navigate(self, url: str) -> Dict[str, Any]:
        self.driver.goto(url)
        content = self.driver.content()
        res = {
            "url": getattr(self.driver, "url", url),
            "snapshot": self._format_snapshot(content),
        }
        res.update(self._get_errors_and_failures())
        return res

    def click(self, selector: str) -> Dict[str, Any]:
        self.driver.click(selector)
        content = self.driver.content()
        res = {
            "url": getattr(self.driver, "url", ""),
            "snapshot": self._format_snapshot(content),
        }
        res.update(self._get_errors_and_failures())
        return res

    def fill(self, selector: str, value: str) -> Dict[str, Any]:
        self.driver.fill(selector, value)
        content = self.driver.content()
        res = {
            "snapshot": self._format_snapshot(content),
        }
        res.update(self._get_errors_and_failures())
        return res

    def screenshot(self, path: str = "artifacts/screenshot.png") -> Evidence:
        saved_path = self.driver.screenshot(path)
        return Evidence(
            type=EvidenceType.SCREENSHOT,
            content=str(saved_path or path),
        )

    def console_errors(self) -> List[Dict[str, Any]]:
        messages = getattr(self.driver, "console_messages", [])
        errors = [m for m in messages if m.get("type") == "error"]
        if self.delimit:
            return [{"type": "error", "text": self.fence.strip_breakout(m.get("text", ""))} for m in errors]
        return errors

    def snapshot(self) -> str:
        return self._format_snapshot(self.driver.content())
