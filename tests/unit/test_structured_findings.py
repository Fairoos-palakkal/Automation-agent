"""Unit tests for Structured Findings and Automatic Observation Evidence Capture (Ticket T-11).

Verifies:
1. report_finding accepts structured fields {summary, expected, actual, selector_or_url, step_ids}.
2. Runtime builds Evidence from real tool observation and ignores model-fabricated evidence_content strings.
3. Findings link concrete, non-fingerprint steps referencing StepLog IDs (step-1, step-2).
4. Concrete steps contain executable tools, selectors, and arguments for replay.
"""
import pytest

from qa_cc.agents.baseline import BaselineAgent
from qa_cc.agents.loop import AgentLoop
from qa_cc.agents.step_log import StepLog
from qa_cc.gateway.gateway import ToolGateway, ToolDefinition
from qa_cc.llm.client import LLMClient
from qa_cc.llm.fake_provider import FakeProvider
from qa_cc.verdict.evidence import EvidenceType, Finding


def make_call(tool_name: str, args: dict):
    return {
        "id": "c1",
        "model": "fake-model",
        "choices": [{
            "message": {
                "role": "assistant",
                "tool_calls": [{
                    "id": f"tc-{tool_name}",
                    "type": "function",
                    "function": {"name": tool_name, "arguments": args},
                }],
            }
        }],
        "usage": {"total_tokens": 10},
    }


class TestStructuredFindingsAndEvidenceCapture:
    def test_captured_evidence_ignores_fabricated_content(self):
        """Model-supplied evidence_content is ignored in favor of real gateway observation."""
        real_dom = "<html><div id='cart'>Total: -5</div></html>"
        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(
            name="navigate",
            handler=lambda url: {"url": url, "snapshot": real_dom},
            is_url_action=True,
        ))

        provider = FakeProvider(responses=[
            make_call("navigate", {"url": "http://localhost:3000/cart.html"}),
            make_call("report_finding", {
                "summary": "Cart allows negative balance",
                "expected": "Cart total >= 0",
                "actual": "Cart total is -5",
                "selector_or_url": "#cart",
                "evidence_content": "HALLUCINATED_FABRICATED_STRING_FROM_LLM",
                "evidence_type": "dom_snapshot",
            }),
            make_call("finish", {"summary": "Done"}),
        ])

        client = LLMClient(provider=provider)
        agent = BaselineAgent(llm_client=client, gateway=gateway)
        result = agent.run(objective="Test cart negative total", target="http://localhost:3000/cart.html")

        assert len(result.findings) == 1
        finding = result.findings[0]
        assert finding.summary == "Cart allows negative balance"
        assert finding.expected == "Cart total >= 0"
        assert finding.actual == "Cart total is -5"
        assert finding.selector_or_url == "#cart"

        # Evidence MUST be captured from the real DOM snapshot, not hallucinated string
        assert len(finding.evidence) >= 1
        ev = finding.evidence[0]
        assert "HALLUCINATED_FABRICATED_STRING_FROM_LLM" not in ev.content
        assert "Total: -5" in ev.content
        assert ev.type == EvidenceType.DOM_SNAPSHOT

    def test_findings_contain_non_fingerprint_steps_with_steplog_ids(self):
        """Findings in findings.json contain non-empty, non-fingerprint step lists referencing StepLog IDs."""
        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(
            name="navigate",
            handler=lambda url: {"url": url, "snapshot": "<html>Catalog</html>"},
            is_url_action=True,
        ))
        gateway.register_tool(ToolDefinition(
            name="click",
            handler=lambda selector: {"snapshot": "<html>Filter Applied</html>"},
        ))

        provider = FakeProvider(responses=[
            make_call("navigate", {"url": "http://localhost:3000/catalog.html"}),
            make_call("click", {"selector": "button#apply-filter"}),
            make_call("report_finding", {
                "summary": "Catalog filter crash",
                "expected": "Items filtered",
                "actual": "Unhandled error",
                "selector_or_url": "button#apply-filter",
            }),
            make_call("finish", {"summary": "Done"}),
        ])

        client = LLMClient(provider=provider)
        agent = BaselineAgent(llm_client=client, gateway=gateway)
        result = agent.run(objective="Test filter", target="http://localhost:3000/catalog.html")

        assert len(result.findings) == 1
        finding = result.findings[0]
        assert len(finding.steps) == 2

        # Verify steps are concrete StepLog dicts, not hash-only fingerprints
        step1, step2 = finding.steps[0], finding.steps[1]
        assert step1["step_id"] == "step-1"
        assert step1["tool"] == "navigate"
        assert step1["args"] == {"url": "http://localhost:3000/catalog.html"}
        assert "fingerprint" not in step1 or "step_id" in step1

        assert step2["step_id"] == "step-2"
        assert step2["tool"] == "click"
        assert step2["args"] == {"selector": "button#apply-filter"}

    def test_report_finding_step_ids_filtering(self):
        """When the agent passes step_ids, only those steps from StepLog are attached to the Finding."""
        gateway = ToolGateway()
        gateway.register_tool(ToolDefinition(name="navigate", handler=lambda url: {"snapshot": "page"}))
        gateway.register_tool(ToolDefinition(name="click", handler=lambda selector: {"snapshot": "clicked"}))

        provider = FakeProvider(responses=[
            make_call("navigate", {"url": "http://localhost:3000"}),
            make_call("click", {"selector": "#buggy-btn"}),
            make_call("report_finding", {
                "summary": "Specific button failure",
                "step_ids": ["step-2"],
            }),
            make_call("finish", {"summary": "Done"}),
        ])

        client = LLMClient(provider=provider)
        agent = BaselineAgent(llm_client=client, gateway=gateway)
        result = agent.run(objective="Test button", target="http://localhost:3000")

        finding = result.findings[0]
        assert len(finding.steps) == 1
        assert finding.steps[0]["step_id"] == "step-2"
        assert finding.steps[0]["tool"] == "click"
