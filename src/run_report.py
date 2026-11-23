"""Printable PDF report for one analysed run: brand comparison with 95% intervals, gaps found
and every answer with its brand mentions and sources. Downloaded from the dashboard."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.api import queries
from src.config import ROOT_DIR, get_settings
from src.db import get_conn
from src.opportunities.repository import list_opportunities
from src.report_pdf import (
    BRAND,
    CSS,
    esc,
    load_real,
    pct,
    review_box,
    section_real,
    table,
    to_pdf,
)

REPORT_DIR = ROOT_DIR / "reports" / "runs"
ENGINE = {"perplexity": "Perplexity", "openai": "ChatGPT", "gemini": "Gemini"}


def _headline(real: dict[str, Any], target: str) -> str:
    rows = [
        v for v in real["visibility"] if v["category"] == "ALL" and v["mention_rate"] is not None
    ]
    me = next((v for v in rows if v["brand"] == target), None)
    if not me or not rows:
        return "No brand visibility was measured for this run."
    lead = max(rows, key=lambda v: float(v["mention_rate"]))
    engine = ENGINE.get(real["run"]["provider"], real["run"]["provider"])
    text = f"On {engine}, {target} appears in {pct(float(me['mention_rate']), 0)} of answers."
    if lead["brand"] == target:
        return text + " That leads every competitor measured."
    return text + f" {lead['brand']} leads at {pct(float(lead['mention_rate']), 0)}."


def _gaps(opps: list[dict[str, Any]]) -> str:
    if not opps:
        return (
            "<p>No gaps were found for this run. Either Sephora India keeps up with its "
            "competitors here, or the run is too small for the rules to be confident.</p>"
        )
    rows = [[f"{o['priority_score'] or 0:.0f}", esc(o["title"]), pct(o["confidence"], 0),
             esc(o["effort"] or "–"), esc(o["action"] or "–"),
             esc((o["rec_status"] or "proposed") + (f" by {o['reviewed_by']}"
                                                    if o["reviewed_by"] else ""))]
            for o in opps]  # fmt: skip
    return table(["Priority", "Gap", "Confidence", "Effort", "Suggested action", "Review"],
                 rows, {0, 2})  # fmt: skip


def _answers(responses: list[dict[str, Any]]) -> str:
    rows = []
    for r in responses:
        if r["error"]:
            brands = '<span class="bad">failed</span>'
            answer = esc(r["error"][:160])
        else:
            brands = (
                ", ".join(
                    f'<span style="color:{BRAND.get(m["brand"], "#16181d")};font-weight:600">'
                    f"{esc(m['brand'])}{' #' + str(m['rank']) if m['rank'] else ''}</span>"
                    for m in r["mentions"]
                )
                or "none"
            )
            text = (r["answer_text"] or "").replace("\n", " ")
            answer = esc(text[:420]) + ("…" if len(text) > 420 else "")
        rows.append([esc(r["prompt_id"]), esc(r["prompt"]), brands, len(r["citations"]),
                     f'<span class="snip">{answer}</span>'])  # fmt: skip
    return table(["Id", "Question", "Brands named (position)", "Sources", "Answer (start)"],
                 rows, {3})  # fmt: skip


def build_run_html(run_id: str) -> str:
    real = load_real(run_id)
    if not real:
        raise ValueError(f"Run {run_id} not found")
    if not real["run"]["diagnosed"]:
        raise ValueError("Measure this run before downloading its report.")
    settings = get_settings()
    target = settings.project.target.name
    with get_conn() as conn:
        opps = list_opportunities(conn, run_id)
        responses = queries.list_responses(conn, run_id, 500)
    run_ = real["run"]
    engine = ENGINE.get(run_["provider"], run_["provider"])
    kind = {"baseline": "question panel", "adhoc": "own questions",
            "retest": "re-test"}.get(run_["run_type"], run_["run_type"])  # fmt: skip
    generated = datetime.now(UTC).strftime("%d %b %Y %H:%M UTC")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Visibility report — {esc(engine)} {esc(str(run_["started_at"])[:10])}</title>
<style>{CSS}
.snip {{ color: #4d5260; font-size: 8pt; }}
.answers td:nth-child(1) {{ white-space: nowrap; width: 9%; }}
.answers td:nth-child(2) {{ width: 24%; }}
.answers td:nth-child(3) {{ width: 16%; }}
.answers td:nth-child(4) {{ width: 7%; }}
.headline {{ font-size: 16pt; font-weight: 600; line-height: 1.3; margin: 12px 0; }}</style>
</head><body>
<div class="cover">
  <h1>Visibility report</h1>
  <div><b>Beyond the Search Bar</b> — how AI answer engines present {esc(target)} against
  {esc(", ".join(b.name for b in settings.project.competitors))}.</div>
  <div class="meta">{esc(engine)} {esc(run_["model"])} · {esc(kind)} (panel
  {esc(run_["panel_version"])}) · run started {esc(str(run_["started_at"])[:16])} UTC ·
  {run_["n_responses"] - run_["n_errors"]} answers, {run_["n_errors"]} failed calls ·
  run id {esc(run_["run_id"])} · generated {generated}</div>
</div>
<p class="headline">{esc(_headline(real, target))}</p>
<p class="note">Figures describe these questions, this engine and this date only. Mentions and
list positions are found with fixed rules whose accuracy is measured in the evaluation report
(Check accuracy page). List positions are the less reliable of the two, especially for answers
with intro headings, tables or comparison sections; check them before acting on ranking figures.
</p>
{section_real(real, title="1. Brand comparison", lead="This run")}
<section class="break">
  <h2>2. Gaps found ({len(opps)})</h2>
  <p>Ranked by priority (severity × confidence ÷ effort). Each gap is backed by the answers that
  show it; approve or reject actions on the Find gaps page.</p>
  {_gaps(opps)}
  {review_box("Gaps")}
</section>
<section class="break">
  <h2>3. Every answer ({len(responses)})</h2>
  <p class="note">Brands named in each answer with their list position, the number of sources it
  cited and the start of the answer. Full raw answers are stored in the database.</p>
  <div class="answers">{_answers(responses)}</div>
</section>
<section>
  <h2>Sign-off</h2>
  <table class="sign"><tr><td>Reviewed by</td><td></td><td>Date</td><td></td></tr>
  <tr><td>Comments</td><td colspan="3" style="height:70px"></td></tr></table>
</section>
</body></html>"""


def build_run_report(run_id: str, out_dir: Path = REPORT_DIR) -> Path:
    """Write the run report. Returns the PDF, or the HTML if no Chrome/Edge is installed."""
    page = build_run_html(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    html_path = out_dir / f"run_report_{run_id[:8]}_{stamp}.html"
    pdf_path = html_path.with_suffix(".pdf")
    html_path.write_text(page, encoding="utf-8")
    try:
        to_pdf(html_path, pdf_path)
        return pdf_path
    except RuntimeError:
        return html_path
