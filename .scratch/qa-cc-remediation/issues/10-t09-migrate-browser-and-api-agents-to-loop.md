# 10: T-09: Migrate Browser and API Agents to Shared Loop (Contract)

**What to build:** Migrate `BrowserAgent` and `ApiAgent` to use the shared `AgentLoop`. Delete the duplicated loop implementations, unifying tool parsing, step logging, and error handling across all agents.

**Blocked by:** 09: T-08: Shared AgentLoop and StepLog Architecture (Expand)

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Duplicated agent loops in browser.py and api.py are eliminated (~500 fewer lines)
- [ ] All unit and contract tests for BrowserAgent and ApiAgent pass on the shared AgentLoop
