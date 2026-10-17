"""Static HTML report generator for agent run findings and evidence."""
import html
from pathlib import Path
from typing import Optional, Union

from qa_cc.agents.baseline import RunResult
from qa_cc.security.scrubber import Scrubber


def generate_report(
    run_result: RunResult,
    output_path: Union[str, Path],
    scrubber: Optional[Scrubber] = None,
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    active_scrubber = scrubber or Scrubber()

    findings_html = ""
    if not run_result.findings:
        findings_html = "<div class='no-findings'><p>No findings recorded during this run.</p></div>"
    else:
        for f in run_result.findings:
            esc_id = html.escape(active_scrubber.scrub(str(f.id)))
            esc_summary = html.escape(active_scrubber.scrub(str(f.summary)))
            verdict_badge = ""
            if f.verdict:
                vtype = f.verdict.type
                vtype_val = vtype.value if hasattr(vtype, "value") else str(vtype)
                esc_vtype = html.escape(active_scrubber.scrub(str(vtype_val)))
                color = "#28a745" if vtype_val == "PASS" else "#dc3545" if vtype_val == "FAIL" else "#ffc107"
                verdict_badge = f"<span class='badge' style='background:{color};'>{esc_vtype}</span>"
            else:
                verdict_badge = "<span class='badge' style='background:#6c757d;'>UNVERIFIED</span>"

            evidence_items = ""
            for ev in f.evidence:
                esc_ev_type = html.escape(active_scrubber.scrub(str(ev.type)))
                esc_ev_content = html.escape(active_scrubber.scrub(str(ev.content)))
                evidence_items += f"""
                <li class="evidence-item">
                    <strong>Type:</strong> <code>{esc_ev_type}</code><br>
                    <strong>Content:</strong> <pre>{esc_ev_content}</pre>
                </li>
                """

            findings_html += f"""
            <div class="finding-card">
                <div class="finding-header">
                    <h3>{esc_id}: {esc_summary}</h3>
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

    is_mock = getattr(run_result, "is_mock", False)
    mock_badge_html = ""
    if is_mock:
        mock_badge_html = "<div style='margin-top:0.5rem;'><span class='badge' style='background:#eab308;color:#000;font-size:0.9rem;padding:0.3rem 0.6rem;font-weight:bold;'>MOCK RUN (SIMULATED)</span></div>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none';">
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
            {mock_badge_html}
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
    out.write_text(html_content, encoding="utf-8")
    return out
