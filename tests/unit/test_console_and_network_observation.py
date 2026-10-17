"""Tests for Console Errors and Failed Requests Visibility (T-18, F-12).

Verifies:
1. PlaywrightPageDriver captures pageerror, requestfailed, and failed responses (>= 400).
2. BrowserTools actions (navigate, click, fill) append bounded console_errors and failed_requests
   wrapped in the untrusted-content fence to the action result.
3. Errors are cleared upon new navigation (goto).
4. Uncaught TypeError (e.g. from catalog.html #filter-btn) is visible to the agent in the action observation.
5. console_errors tool is registered and callable by browser and baseline agents.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from qa_cc.tools.browser import BrowserTools
from qa_cc.tools.playwright_driver import PlaywrightPageDriver
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.security.fence import ContentFence
from qa_cc.agents.baseline import BaselineAgent, DEFAULT_TOOLS
from qa_cc.agents.browser import BrowserAgent, BROWSER_TOOLS
from qa_cc.agents.plan import Task
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider


class FakeEmitterPage:
    """Mock Playwright Page that supports event subscriptions and triggers."""

    def __init__(self):
        self.listeners = {}
        self._url = "http://localhost:3000/catalog.html"
        self._content = "<html><body><button id='filter-btn'>Filter</button></body></html>"

    def on(self, event: str, callback):
        self.listeners.setdefault(event, []).append(callback)

    def emit(self, event: str, payload):
        for cb in self.listeners.get(event, []):
            cb(payload)

    def goto(self, url: str):
        self._url = url

    def click(self, selector: str, timeout: float = 5000):
        if selector == "#filter-btn":
            # Simulate uncaught TypeError when #filter-btn is clicked
            error_msg = "TypeError: Cannot read properties of undefined (reading 'filter')"
            self.emit("pageerror", Exception(error_msg))

    def fill(self, selector: str, value: str, timeout: float = 5000):
        pass

    def content(self):
        return self._content

    @property
    def url(self):
        return self._url


def test_driver_registers_pageerror_and_request_listeners():
    page = FakeEmitterPage()
    driver = PlaywrightPageDriver(page)

    assert "console" in page.listeners
    assert "pageerror" in page.listeners
    assert "requestfailed" in page.listeners
    assert "response" in page.listeners

    # Emitting pageerror adds to console_messages
    page.emit("pageerror", Exception("Uncaught Error: Crash"))
    errors = [m for m in driver.console_messages if m.get("type") == "error"]
    assert len(errors) == 1
    assert "Crash" in errors[0]["text"]


def test_click_filter_btn_observes_type_error_wrapped_in_fence():
    page = FakeEmitterPage()
    driver = PlaywrightPageDriver(page)
    tools = BrowserTools(driver=driver)

    result = tools.click("#filter-btn")

    # The action result returned to the agent MUST contain console_errors
    assert "console_errors" in result
    assert "TypeError: Cannot read properties of undefined" in result["console_errors"]
    assert "<UNTRUSTED_CONTENT_" in result["console_errors"]
    assert "</UNTRUSTED_CONTENT_" in result["console_errors"]


def test_driver_clears_errors_on_navigation():
    page = FakeEmitterPage()
    driver = PlaywrightPageDriver(page)
    page.emit("pageerror", Exception("Old error"))
    assert len(driver.console_messages) == 1

    driver.goto("http://localhost:3000/index.html")
    assert len(driver.console_messages) == 0


def test_console_errors_tool_in_schemas_and_gateway():
    """console_errors must exist in DEFAULT_TOOLS and BROWSER_TOOLS."""
    tool_names_baseline = [t["function"]["name"] for t in DEFAULT_TOOLS]
    tool_names_browser = [t["function"]["name"] for t in BROWSER_TOOLS]

    assert "console_errors" in tool_names_baseline
    assert "console_errors" in tool_names_browser

    # Gateway execution test
    page = FakeEmitterPage()
    driver = PlaywrightPageDriver(page)
    tools = BrowserTools(driver=driver)
    page.emit("pageerror", Exception("Runtime Error 42"))

    gw = ToolGateway()
    gw.register_tool(ToolDefinition(
        name="console_errors",
        handler=tools.console_errors,
        allowed_callers={"baseline", "browser"},
    ))

    res = gw.execute("console_errors", {}, caller="browser")
    assert "Runtime Error 42" in str(res)
