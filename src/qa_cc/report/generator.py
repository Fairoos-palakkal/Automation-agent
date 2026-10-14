"""Static HTML report generator for agent run findings and evidence."""
from pathlib import Path
from typing import Union

from qa_cc.agents.baseline import RunResult


def generate_report(run_result: RunResult, output_path: Union[str, Path]) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    findings_html = ""
    if not run_result.findings:
        findings_html = "<div class='no-findings'><p>No findings recorded during this run.</p></div>"
    else:
        for f in run_result.findings:
            verdict_badge = ""
            if f.verdict:
                vtype = f.verdict.type
                color = "#28a745" if vtype == "PASS" else "#dc3545" if vtype == "FAIL" else "#ffc107"
                verdict_badge = f"<span class='badge' style='background:{color};'>{vtype}</span>"
            else:
                verdict_badge = "<span class='badge' style='background:#6c757d;'>UNVERIFIED</span>"

            evidence_items = ""
            for ev in f.evidence:
                evidence_items += f"""
                <li class="evidence-item">
                    <strong>Type:</strong> <code>{ev.type}</code><br>
                    <strong>Content:</strong> <pre>{ev.content}</pre>
                </li>
                """

            findings_html += f"""
            <div class="finding-card">
                <div class="finding-header">
                    <h3>{f.id}: {f.summary}</h3>
                    {verdict_badge}
                </div>
                <div class="evidence-list">
                    <h4>Attached Evidence:</h4>
                    <ul>
                        {evidence_items}
                    </ul>
                </div>
            </div>
            """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Agentic QA Command Center — Run Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        header {{ border-bottom: 1px solid #334155; padding-bottom: 1.5rem; margin-bottom: 2rem; }}
        h1 {{ margin: 0 0 0.5rem 0; color: #38bdf8; font-size: 1.8rem; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }}
        .stat-card {{ background: #1e293b; padding: 1rem; border-radius: 8px; border: 1px solid #334155; }}
        .stat-val {{ font-size: 1.5rem; font-weight: bold; color: #38bdf8; }}
        .stat-label {{ font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; }}
        .finding-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }}
        .finding-header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 0.75rem; margin-bottom: 1rem; }}
        .badge {{ padding: 0.25rem 0.6rem; border-radius: 4px; font-weight: bold; font-size: 0.85rem; color: #fff; }}
        pre {{ background: #0f172a; padding: 0.75rem; border-radius: 4px; overflow-x: auto; color: #cbd5e1; }}
        code {{ background: #334155; padding: 0.2rem 0.4rem; border-radius: 4px; }}
        ul {{ padding-left: 1.2rem; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Agentic QA Command Center</h1>
            <p>Autonomous Exploration & Evidence Capture Report</p>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-val">{len(run_result.findings)}</div>
                <div class="stat-label">Findings</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{run_result.actions_count}</div>
                <div class="stat-label">Actions</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{run_result.tokens_used}</div>
                <div class="stat-label">Tokens</div>
            </div>
            <div class="stat-card">
                <div class="stat-val">{"YES" if run_result.budget_exceeded else "NO"}</div>
                <div class="stat-label">Budget Exceeded</div>
            </div>
        </div>

        <h2>Recorded Findings</h2>
        {findings_html}
    </div>
</body>
</html>
"""
    out.write_text(html, encoding="utf-8")
    return out
