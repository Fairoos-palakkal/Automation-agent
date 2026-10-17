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


class PermissionRequired(Exception):
    """Raised when an action requires explicit permissions that are not granted."""
    pass


@dataclass
class ToolDefinition:
    name: str
    handler: Callable[..., Any]
    is_url_action: bool = False
    required_permission: Optional[str] = None
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
    ):
        self.allowlist = allowlist or ["localhost", "127.0.0.1"]
        self.granted_permissions = set(granted_permissions or [])
        self.trace_writer = trace_writer
        self.secret_keys = secret_keys or []
        self.scrubber = scrubber or Scrubber(secret_env_vars=self.secret_keys)
        self._registry: Dict[str, ToolDefinition] = {}

    def register_tool(self, tool_def: ToolDefinition) -> None:
        self._registry[tool_def.name] = tool_def

    def grant_permission(self, permission: str) -> None:
        self.granted_permissions.add(permission)

    def revoke_permission(self, permission: str) -> None:
        self.granted_permissions.discard(permission)

    def _is_url_allowed(self, url: str) -> bool:
        return is_url_allowed(url, self.allowlist)

    def _scrub_obj(self, obj: Any) -> Any:
        return self.scrubber.scrub(obj)

    def execute(self, tool_name: str, args: Dict[str, Any]) -> Any:
        if tool_name not in self._registry:
            raise ToolNotFound(f"Tool '{tool_name}' is not registered in ToolGateway.")

        tool_def = self._registry[tool_name]

        # Permission check
        if tool_def.required_permission and tool_def.required_permission not in self.granted_permissions:
            raise PermissionRequired(
                f"Tool '{tool_name}' requires permission '{tool_def.required_permission}' which has not been granted."
            )

        # Allowlist check for url actions
        if tool_def.is_url_action:
            url = args.get("url", "")
            if not self._is_url_allowed(url):
                raise TargetNotAllowed(f"Target URL '{url}' is not permitted by allowlist: {self.allowlist}")

        # Execute handler
        result = tool_def.handler(**args)

        # Trace recording
        if self.trace_writer:
            scrubbed_args = self._scrub_obj(args)
            scrubbed_result = self._scrub_obj(result)
            self.trace_writer.record_tool_call(
                tool_name=tool_name,
                args=scrubbed_args,
                result=scrubbed_result,
            )

        return result
