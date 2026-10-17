# 21: T-20: Per-Agent Caller Permissions and Gateway-Controlled Screenshots

**What to build:** Enforce caller permissions in ToolGateway (`allowed_callers` per ToolDefinition). Block BrowserAgent from calling HTTP tools and ApiAgent from calling browser tools. The screenshot tool ignores model-supplied paths and writes to `artifacts/<run_id>/<step_id>.png`.

**Blocked by:** 10: T-09: Migrate Browser and API Agents to Shared Loop (Contract), 11: T-10: Run Identity, Directory Layout, and Validated TraceEntry Schema

**Status:** ready-for-agent

## Acceptance criteria

- [ ] BrowserAgent caller attempting to execute `http_request` raises PermissionRequired
- [ ] Screenshot file paths are unique per step and cannot overwrite arbitrary system paths
