"""Playwright driver adapter wrapping Playwright Page for BrowserTools."""
from typing import Any, Dict, List, Optional
from qa_cc.gateway.allowlist import is_url_allowed
from qa_cc.trace.writer import TraceWriter


class PlaywrightPageDriver:
    """Adapts a Playwright Page instance to the BrowserTools driver interface."""

    def __init__(
        self,
        page: Any,
        allowlist: Optional[List[str]] = None,
        trace_writer: Optional[TraceWriter] = None,
    ):
        self._page = page
        self.allowlist = allowlist or ["localhost", "127.0.0.1"]
        self.trace_writer = trace_writer
        self.denied_requests: List[str] = []
        self.console_messages: List[Dict[str, Any]] = []
        self.failed_requests: List[Dict[str, Any]] = []

        if hasattr(self._page, "on"):
            self._page.on(
                "console",
                lambda msg: self.console_messages.append({
                    "type": getattr(msg, "type", "log"),
                    "text": getattr(msg, "text", str(msg)),
                }),
            )
            self._page.on(
                "pageerror",
                lambda exc: self.console_messages.append({
                    "type": "error",
                    "text": str(exc),
                }),
            )
            self._page.on(
                "requestfailed",
                lambda req: self.failed_requests.append({
                    "url": getattr(req, "url", ""),
                    "method": getattr(req, "method", "GET"),
                    "failure": getattr(req, "failure", "Request failed"),
                }),
            )

            def _on_response(resp: Any) -> None:
                try:
                    status = getattr(resp, "status", 200)
                    if status >= 400:
                        self.failed_requests.append({
                            "url": getattr(resp, "url", ""),
                            "status": status,
                            "status_text": getattr(resp, "status_text", ""),
                        })
                except Exception:
                    pass

            self._page.on("response", _on_response)

        self._setup_route_interception()

    def _setup_route_interception(self) -> None:
        route_target = getattr(self._page, "context", None)
        if not (route_target and hasattr(route_target, "route")):
            route_target = self._page

        if hasattr(route_target, "route"):
            def handle_route(route: Any, request: Any = None) -> None:
                req = getattr(route, "request", request)
                url = getattr(req, "url", "")
                if not is_url_allowed(url, self.allowlist):
                    self.denied_requests.append(url)
                    if self.trace_writer:
                        self.trace_writer.record_tool_call(
                            tool_name="browser_network_denial",
                            args={"url": url},
                            result={"status": "aborted", "reason": "TargetNotAllowed"},
                        )
                    route.abort()
                else:
                    route.continue_()

            try:
                route_target.route("**/*", handle_route)
            except Exception:
                pass

    def goto(self, url: str) -> Any:
        self.console_messages.clear()
        self.failed_requests.clear()
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
