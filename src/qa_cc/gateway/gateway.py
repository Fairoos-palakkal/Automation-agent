"""ToolGateway — Single enforcement point for tool execution.

Enforces:
1. Tool registry and existence checks (ToolNotFound).
2. URL allowlist for network/browser actions (TargetNotAllowed).
3. Secret scrubbing from arguments before tracing.
4. Permission gating for sensitive operations (PermissionRequired).
5. Automatic recording of tool calls to TraceWriter.
"""
from dataclasses import dataclass, field
import os
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse

from qa_cc.trace.writer import TraceWriter
from qa_cc.gateway.allowlist import is_url_allowed
from qa_cc.security.scrubber import Scrubber


class ToolNotFound(Exception):
    """Raised when an unregistered tool is invoked."""
    pass


class TargetNotAllowed(Exception):
    """Raised when an action attempts to target a non-allowlisted host/URL."""
    pass


from pathlib import Path


class PermissionRequired(Exception):
    """Raised when an action requires explicit permissions that are not granted."""
    pass


@dataclass
class ToolDefinition:
    name: str
    handler: Callable[..., Any]
    is_url_action: bool = False
    required_permission: Optional[str] = None
    allowed_callers: Optional[Set[str]] = None
    description: str = ""
    parameters: Optional[Dict[str, Any]] = None


class ToolGateway:
    def __init__(
        self,
        allowlist: Optional[List[str]] = None,
        granted_permissions: Optional[Set[str]] = None,
        trace_writer: Optional[TraceWriter] = None,
        secret_keys: Optional[List[str]] = None,
        scrubber: Optional[Scrubber] = None,
        artifacts_dir: Optional[Path | str] = None,
    ):
        self.allowlist = allowlist or ["localhost", "127.0.0.1"]
        self.granted_permissions = set(granted_permissions or [])
        self.trace_writer = trace_writer
        self.secret_keys = secret_keys or []
        self.scrubber = scrubber or Scrubber(secret_env_vars=self.secret_keys)
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir else None
        self._screenshot_counter = 0
        self._registry: Dict[str, ToolDefinition] = {}

    def register_tool(self, tool_def: ToolDefinition) -> None:
        self._registry[tool_def.name] = tool_def

    def register_screenshot_tool(
        self,
        screenshot_saver: Callable[[str], Any],
        allowed_callers: Optional[Set[str]] = None,
    ) -> None:
        """Register the screenshot tool where gateway owns the output path."""
        def _handler(**kwargs: Any) -> Dict[str, Any]:
            self._screenshot_counter += 1
            step_num = self._screenshot_counter
            if self.artifacts_dir:
                self.artifacts_dir.mkdir(parents=True, exist_ok=True)
                dest = self.artifacts_dir / f"screenshot_{step_num}.png"
            else:
                dest = Path(f"artifacts/screenshot_{step_num}.png")
                dest.parent.mkdir(parents=True, exist_ok=True)
            saved = screenshot_saver(str(dest))
            return {"path": str(dest), "saved": saved}

        self.register_tool(
            ToolDefinition(
                name="screenshot",
                handler=_handler,
                allowed_callers=allowed_callers or {"baseline", "browser"},
                description="Capture a screenshot Evidence of the current browser page.",
                parameters={"type": "object", "properties": {}},
            )
        )

    def grant_permission(self, permission: str) -> None:
        self.granted_permissions.add(permission)

    def revoke_permission(self, permission: str) -> None:
        self.granted_permissions.discard(permission)

    def _is_url_allowed(self, url: str) -> bool:
        return is_url_allowed(url, self.allowlist)

    def _scrub_obj(self, obj: Any) -> Any:
        return self.scrubber.scrub(obj)

    def execute(self, tool_name: str, args: Dict[str, Any], caller: Optional[str] = None) -> Any:
        result = None
        error = None
        denied = False
        denial_reason = None

        try:
            if tool_name not in self._registry:
                denied = True
                denial_reason = f"Tool '{tool_name}' is not registered in ToolGateway."
                raise ToolNotFound(denial_reason)

            tool_def = self._registry[tool_name]

            # Caller permission check
            if tool_def.allowed_callers is not None and caller is not None:
                if caller not in tool_def.allowed_callers:
                    denied = True
                    denial_reason = (
                        f"Caller '{caller}' is not authorized to use tool '{tool_name}'. "
                        f"Allowed callers: {sorted(tool_def.allowed_callers)}"
                    )
                    raise PermissionRequired(denial_reason)

            # Explicit permission check
            if tool_def.required_permission and tool_def.required_permission not in self.granted_permissions:
                denied = True
                denial_reason = (
                    f"Tool '{tool_name}' requires permission '{tool_def.required_permission}' which has not been granted."
                )
                raise PermissionRequired(denial_reason)

            # Allowlist check for url actions
            if tool_def.is_url_action:
                url = args.get("url", "")
                if not self._is_url_allowed(url):
                    denied = True
                    denial_reason = f"Target URL '{url}' is not permitted by allowlist: {self.allowlist}"
                    raise TargetNotAllowed(denial_reason)

            # Execute handler
            result = tool_def.handler(**args)
            return result
        except Exception as e:
            error = str(e)
            raise
        finally:
            if self.trace_writer:
                scrubbed_args = self._scrub_obj(args)
                scrubbed_result = self._scrub_obj(result) if result is not None else None
                entry_type = "tool_call_denied" if denied else "tool_call"
                payload = {
                    "type": entry_type,
                    "tool_name": tool_name,
                    "args": scrubbed_args,
                    "result": scrubbed_result,
                    "model_id": "agent-gateway",
                    "tokens": 0,
                    "ok": error is None,
                }
                if caller is not None:
                    payload["caller"] = caller
                if error is not None:
                    payload["error"] = error
                if denied and denial_reason:
                    payload["denial_reason"] = denial_reason
                self.trace_writer.record(payload)

