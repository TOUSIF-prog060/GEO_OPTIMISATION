"""Build the printable evaluation report and print it to PDF.

    python -m evals.report_pdf              # offline evaluation + latest real run from the DB
    python -m evals.report_pdf --no-db      # sandbox results only
    python -m evals.report_pdf --live       # also run the live model test (real calls)

Output: reports/evals/evaluation_report_<timestamp>.pdf (and the .html next to it).
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.run import OUT_DIR, run
from src.config import ROOT_DIR
from src.report_pdf import (
    ACCENT,
    BAD,
    BRAND,
    CSS,
    GOOD,
    esc,
    grouped,
    hbars,
    load_real,
    matrix,
    ok,
    pct,
    review_box,
    section_real,
    table,
    to_pdf,
)

# ---------------------------------------------------------------- sections


def section_summary(r: dict[str, Any]) -> str:
    m, g = r["measurement"]["metrics"], r["gaps"]["metrics"]
    a, mt = r["agent"]["metrics"], r["metrics"]["metrics"]
    live = r.get("live_model", {}).get("metrics", {})
    rows = [
        ("Brand mention F1", m["mention"]["f1"], GOOD),
        ("Brand mention precision", m["mention"]["precision"], GOOD),
        ("Brand mention recall", m["mention"]["recall"], GOOD),
        ("Citation domain accuracy", m["citations"]["domain_accuracy"], GOOD),
        ("Citation owner accuracy", m["citations"]["owner_accuracy"], GOOD),
        ("Metric calculations correct", mt["accuracy"], GOOD),
        ("Agent scenarios passed", a["pass_rate"], GOOD),
        ("Gap detection recall", g["recall"], GOOD),
        ("Gap detection precision", g["precision"], ACCENT),
        ("List position: found when ranked", m["rank"]["ranked_found"], ACCENT),
        ("List position: exact match (all)", m["rank"]["exact_match"], ACCENT),
        ("List position: exact when ranked", m["rank"]["ranked_exact"], ACCENT),
        ("Live model success rate", live.get("success_rate"), ACCENT),
    ]
    tiles = [
        ("Mention F1", pct(m["mention"]["f1"], 0), f"{m['brand_decisions']} brand decisions"),
        ("List position exact", pct(m["rank"]["ranked_exact"], 0),
         f"when truly ranked (n={m['rank']['n_ranked']})"),
        ("Metric checks", f"{mt['correct']}/{mt['checks']}", "hand-computed values"),
        ("Gap detection", f"{pct(g['precision'], 0)} / {pct(g['recall'], 0)}",
         "precision / recall"),
        ("Agent", f"{a['passed']}/{a['scenarios']}", "scenarios passed"),
    ]  # fmt: skip
    tile_html = "".join(
        f'<div class="tile"><div class="tl">{esc(t)}</div><div class="tv">{v}'
        f'</div><div class="ts">{esc(s)}</div></div>'
        for t, v, s in tiles
    )
    return f"""
<section>
  <h2>1. Summary scorecard</h2>
  <div class="tiles">{tile_html}</div>
  <p class="note">Every evaluated parameter on one scale (100% = perfect). Green bars are at or
  near 100%; plum bars are the areas that need work. Live model: {
        "not measured (daily quota exhausted)"
        if live.get("success_rate") is None
        else pct(live.get("success_rate")) + " of calls succeeded"
    }.</p>
  {hbars(rows)}
  {review_box("Summary")}
</section>"""


def section_mentions(r: dict[str, Any]) -> str:
    m = r["measurement"]
    mm = m["metrics"]["mention"]
    conf = {("Mentioned", "Mentioned"): mm["tp"], ("Mentioned", "Not mentioned"): mm["fn"],
            ("Not mentioned", "Mentioned"): mm["fp"],
            ("Not mentioned", "Not mentioned"): mm["tn"]}  # fmt: skip
    per_brand = []
    for b in BRAND:
        ds = [d for d in m["decisions"] if d["brand"] == b]
        tp = sum(d["truth_mentioned"] and d["pred_mentioned"] for d in ds)
        fp = sum(not d["truth_mentioned"] and d["pred_mentioned"] for d in ds)
        fn = sum(d["truth_mentioned"] and not d["pred_mentioned"] for d in ds)
        p = tp / (tp + fp) if tp + fp else None
        rc = tp / (tp + fn) if tp + fn else None
        per_brand.append((b, p, rc, len(ds)))
    chart = grouped(["Precision", "Recall"],
                    {b: [p, rc] for b, p, rc, _ in per_brand}, BRAND)  # fmt: skip
    return f"""
<section>
  <h2>2. Brand mention detection</h2>
  <p>{mm["tp"] + mm["fp"] + mm["fn"] + mm["tn"]} decisions: each of 3 brands in each of
  {m["metrics"]["cases"]} test answers, including look-alike words (tiramisu, tirade, Tirana),
  negations, possessives, domains, upper/lower case and sub-brands.</p>
  <div class="row">
    <div><h3>Confusion matrix (truth × parser)</h3>
      {matrix(["Mentioned", "Not mentioned"], ["Mentioned", "Not mentioned"], conf)}</div>
    <div class="grow"><h3>Precision and recall by brand</h3>{chart}</div>
  </div>
  {
        table(
            ["Brand", "Precision", "Recall", "Decisions"],
            [[b, pct(p), pct(rc), n] for b, p, rc, n in per_brand],
            {1, 2, 3},
        )
    }
  {review_box("Brand mention detection")}
</section>"""


def section_ranks(r: dict[str, Any]) -> str:
    m = r["measurement"]
    rk = m["metrics"]["rank"]
    ds = [d for d in m["decisions"] if d["truth_mentioned"] and d["pred_mentioned"]]
    lab = lambda v: "Not ranked" if v is None else f"#{v}"  # noqa: E731
    rows = ["#1", "#2", "#3", "Not ranked"]
    cols = ["#1", "#2", "#3", "#4", "Not ranked"]
    counts = Counter((lab(d["truth_rank"]), lab(d["pred_rank"])) for d in ds)
    tags: dict[str, list[bool]] = {}
    for d in ds:
        tags.setdefault(d["tag"], []).append(d["truth_rank"] == d["pred_rank"])
    tag_rows = sorted(((t.replace("_", " "), sum(v) / len(v)) for t, v in tags.items()),
                      key=lambda x: x[1])  # fmt: skip
    bars = hbars([(t, v, GOOD if v == 1 else BAD if v == 0 else ACCENT) for t, v in tag_rows],
                 row_h=20)  # fmt: skip
    return f"""
<section class="break">
  <h2>3. List position (rank) extraction</h2>
  <p>For every brand that is mentioned: does the parser give the same position a human would?
  "Not ranked" means the answer names the brand but does not rank it (prose, comparison
  sections, a passing reference).</p>
  <div class="row">
    <div><h3>Truth × parser</h3>{matrix(rows, cols, counts)}
      <p class="note">Green outline = correct. Off-diagonal counts are errors.</p></div>
    <div class="grow">
      {
        table(
            ["Parameter", "Value"],
            [
                ["Exact match, all mentioned brands", pct(rk["exact_match"])],
                [f"Found when truly ranked (n={rk['n_ranked']})", pct(rk["ranked_found"])],
                ["Exact when truly ranked", pct(rk["ranked_exact"])],
                [
                    "Mean absolute error (positions)",
                    f"{rk['mean_abs_error']:.2f}" if rk["mean_abs_error"] is not None else "n/a",
                ],
                [
                    f"Rank given when not ranked (n={rk['n_unranked']})",
                    pct(rk["spurious_rank_rate"]),
                ],
            ],
            {1},
        )
    }</div>
  </div>
  <h3>Accuracy by answer format</h3>
  <p class="note">Share of brand positions correct for each kind of answer. Red = always wrong,
  green = always right.</p>
  {bars}
  {review_box("List position")}
</section>"""


def section_citations_metrics(r: dict[str, Any]) -> str:
    urls = r["measurement"]["urls"]
    url_rows = [[f"<code>{esc(u['url'])}</code>", esc(str(u["expected_domain"])),
                 esc(str(u["got_domain"])), esc(str(u["expected_owner"])),
                 esc(str(u["got_owner"])),
                 ok(u["expected_domain"] == u["got_domain"]
                    and u["expected_owner"] == u["got_owner"])] for u in urls]  # fmt: skip
    checks = r["metrics"]["checks"]
    rate_metrics = [c for c in checks if c["metric"] != "avg_rank"]
    met_rows = [[c["brand"], c["metric"].replace("_", " "),
                 f"{c['expected']:.4f}", f"{(c['got'] or 0):.4f}",
                 ok(abs((c["got"] or 0) - c["expected"]) < 1e-4)] for c in checks]  # fmt: skip
    metric_names = ["mention_rate", "share_of_voice", "citation_share"]
    series = {}
    for b in BRAND:
        series[f"{b}"] = [next((c["got"] for c in rate_metrics
                                if c["brand"] == b and c["metric"] == k), None)
                          for k in metric_names]  # fmt: skip
    chart = grouped([k.replace("_", " ") for k in metric_names], series, BRAND)
    return f"""
<section class="break">
  <h2>4. Citations</h2>
  {table(["URL", "Expected domain", "Parsed", "Expected owner", "Found", "Result"], url_rows)}
  {review_box("Citations")}
  <h2>5. Metric calculations</h2>
  <p>Four known answers and four citations in, metrics out, compared with values worked out by
  hand (mentions: Sephora India 2, Nykaa 3, Tira 1 of 4 answers).</p>
  <h3>Computed values (should match the table)</h3>
  {chart}
  {table(["Brand", "Metric", "Expected", "Computed", "Result"], met_rows, {2, 3})}
  {review_box("Metric calculations")}
</section>"""


def section_gaps_agent(r: dict[str, Any]) -> str:
    g = r["gaps"]
    gm = g["metrics"]
    gap_rows = [[s["scenario"].replace("_", " "), "<br>".join(map(esc, s["expected"])),
                 "<br>".join(map(esc, s["found"])), ok(s["correct"])]
                for s in g["scenarios"]]  # fmt: skip
    counts = hbars([("Correct gaps found (true positives)", gm["tp"], GOOD),
                    ("Unexpected gaps (false positives)", gm["fp"], BAD),
                    ("Planted gaps missed (false negatives)", gm["fn"], BAD)],
                   vmax=max(gm["tp"], gm["fp"], gm["fn"], 1),
                   fmt=lambda v: str(int(v)))  # fmt: skip
    ag = r["agent"]
    ag_rows = [[s["scenario"].replace("_", " "), esc(s["status"]),
                esc(" → ".join(s["path"]) or "—"), f"{s['seconds']:.2f}", ok(s["passed"]),
                esc("; ".join(s["problems"]))] for s in ag["scenarios"]]  # fmt: skip
    times = hbars([(s["scenario"].replace("_", " "), s["seconds"], GOOD if s["passed"] else BAD)
                   for s in ag["scenarios"]],
                  vmax=max(s["seconds"] for s in ag["scenarios"]) or 1,
                  fmt=lambda v: f"{v:.2f}s", row_h=20)  # fmt: skip
    return f"""
<section class="break">
  <h2>6. Gap detection</h2>
  <p>Six scenarios built from test answers, each with a planted gap or none. Precision
  {pct(gm["precision"])}, recall {pct(gm["recall"])}.</p>
  {counts}
  {table(["Scenario", "Expected gaps", "Found", "Result"], gap_rows)}
  {review_box("Gap detection")}
</section>
<section class="break">
  <h2>7. Agent behaviour</h2>
  <p>The real LangGraph workflow, driven by scripted tools with injected failures, in-memory
  checkpoints. {ag["metrics"]["passed"]} of {ag["metrics"]["scenarios"]} scenarios passed.</p>
  {table(["Scenario", "Status", "Steps taken", "Seconds", "Result", "Problems"], ag_rows, {3})}
  <h3>Run time per scenario</h3>
  <p class="note">Two scenarios include the workflow's 2-second retry wait.</p>
  {times}
  {review_box("Agent")}
</section>"""


def section_live(r: dict[str, Any]) -> str:
    lm = r.get("live_model")
    if not lm:
        body = ("<p>Not run in this report (use <code>--live</code>). The last attempt "
                "(23 Nov 2026) was blocked by Gemini's free-tier limit of 20 requests per "
                "model per day: 7 of 9 calls returned HTTP 429.</p>")  # fmt: skip
    elif lm.get("skipped"):
        body = f"<p>Skipped: {esc(lm['skipped'])}</p>"
    else:
        x = lm["metrics"]
        rows = [["Calls", x["calls"]], ["Success rate", pct(x["success_rate"])],
                ["Latency median / p95", f"{x['latency_ms']['median']} / "
                                         f"{x['latency_ms']['p95']} ms"],
                ["Sources per answer", x["sources_per_answer"]],
                ["Target mention rate", pct(x["target_mention_rate"])],
                ["Rank stability", pct(x["rank_stability"])],
                ["Source overlap (Jaccard)", x["source_overlap_jaccard"]]]  # fmt: skip
        rows += [[f"Mention agreement: {b}", pct(v)] for b, v in x["mention_agreement"].items()]
        warn = (
            ""
            if x["stability_reported"]
            else "<p class='bad'>Too few successful repeats to report stability.</p>"
        )
        body = warn + table(["Parameter", "Value"], rows, {1})
    return f"""
<section>
  <h2>8. Live model check</h2>
  <p>Asks real questions several times on one engine and measures reliability, latency and
  how stable mentions, positions and sources are. There is no right answer to score against,
  so this measures consistency, not correctness. Nothing is written to the database.</p>
  {body}
  {review_box("Live model")}
</section>"""


def section_findings() -> str:
    return """
<section class="break">
  <h2>10. Findings and recommended fixes</h2>
  <ol class="findings">
    <li><b>Brand mentions are reliable</b> on every tested format (100% precision and recall).
      A negated mention ("not on Nykaa") counts as a mention by definition; tone is a separate
      label.</li>
    <li><b>List position is the weak spot.</b> An intro heading is counted as item 1 (shifting
      every brand down), bold-numbered lines and tables are not read as lists, and comparison
      answers get positions although nothing is ranked. Average position and ranking gaps can be
      wrong. Fix: parser v2 — skip brand-less headings before a list, read bold numbers and
      tables, give no position in comparison answers; re-run this report.</li>
    <li><b>Ranking gaps need a minimum sample.</b> The rule fired on 2 ranked answers out of 10.
      Fix: require a minimum number of answers in which the brand is ranked.</li>
    <li><b>Metric formulas and the agent are correct</b>: 15/15 hand checks, 11/11 agent
      scenarios, including the human-review gate and failure recovery.</li>
    <li><b>The Gemini free tier allows 20 requests per model per day.</b> A full baseline of
      30 questions × 3 repeats needs a paid key or several days.</li>
    <li><b>Accuracy on real answers is still unmeasured.</b> Label 100 real answers with two
      people (Check accuracy page) to measure it.</li>
  </ol>
  <h2>Sign-off</h2>
  <table class="sign"><tr><td>Reviewed by</td><td></td><td>Date</td><td></td></tr>
  <tr><td>Overall verdict</td><td colspan="3">☐ Accept&nbsp;&nbsp; ☐ Accept with fixes&nbsp;&nbsp;
  ☐ Reject</td></tr><tr><td>Comments</td><td colspan="3" style="height:70px"></td></tr></table>
</section>"""


def section_appendix(r: dict[str, Any]) -> str:
    from evals.gold import MENTION_CASES

    lab = lambda v: "–" if v is None else f"#{v}"  # noqa: E731
    rows = []
    for d in r["measurement"]["decisions"]:
        right = (d["truth_mentioned"] == d["pred_mentioned"]
                 and (not d["truth_mentioned"] or d["truth_rank"] == d["pred_rank"]))  # fmt: skip
        rows.append([d["case"], esc(d["tag"].replace("_", " ")), d["brand"],
                     ("yes " + lab(d["truth_rank"])) if d["truth_mentioned"] else "no",
                     ("yes " + lab(d["pred_rank"])) if d["pred_mentioned"] else "no",
                     ok(right), "☐"])  # fmt: skip
    cases = "".join(f'<div class="case"><b>{c.case_id}</b> <i>{esc(c.tag)}</i>'
                    f"<pre>{esc(c.text) or '(empty answer)'}</pre></div>"
                    for c in MENTION_CASES)  # fmt: skip
    return f"""
<section class="break">
  <h2>Appendix A. Every brand decision ({len(rows)})</h2>
  <p class="note">Expected vs parser for each brand in each test answer. "yes #2" = mentioned
  at position 2; "yes –" = mentioned, not ranked. Tick the last column when checked.</p>
  {table(["Case", "Format", "Brand", "Expected", "Parser", "Result", "✓"], rows)}
</section>
<section class="break">
  <h2>Appendix B. Test answers (gold_v1)</h2>
  <p class="note">Synthetic answers written to probe the rules; the expected values are true by
  construction. Several copy real Gemini formatting.</p>
  <div class="cases">{cases}</div>
</section>"""


def build_html(r: dict[str, Any], real: dict[str, Any] | None) -> str:
    m = r["measurement"]["metrics"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Evaluation report — Beyond the Search Bar</title><style>{CSS}</style></head><body>
<div class="cover">
  <h1>Evaluation report</h1>
  <div><b>Beyond the Search Bar</b> — AI Discovery Intelligence Platform (GEO).
  Sephora India vs Nykaa and Tira, beauty and skincare, India.</div>
  <div class="meta">Generated {esc(r["generated_at"])} · gold set {esc(r["gold_version"])}
  ({m["cases"]} test answers, {m["brand_decisions"]} brand decisions, {m["citations"]["n"]}
  URLs) · {esc(r["sandbox"])}</div>
</div>
<p>This report measures how accurately the platform reads AI answers, calculates metrics,
finds gaps and runs its agent, using test data whose correct answers are known. It is meant
to be checked by hand: every section ends with a review box and the appendix lists every
individual decision.</p>
{section_summary(r)}{section_mentions(r)}{section_ranks(r)}{section_citations_metrics(r)}
{section_gaps_agent(r)}{section_live(r)}{section_real(real)}{section_findings()}
{section_appendix(r)}
</body></html>"""


def build_report(live: bool = False, with_db: bool = True, out_dir: Path = OUT_DIR) -> Path:
    """Run the evaluation and write the PDF (falls back to the HTML if no browser is found).
    Returns the path of the file to hand to the user."""
    r = run(live)
    real = load_real() if with_db else None
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    html_path = out_dir / f"evaluation_report_{stamp}.html"
    pdf_path = out_dir / f"evaluation_report_{stamp}.pdf"
    html_path.write_text(build_html(r, real), encoding="utf-8")
    try:
        to_pdf(html_path, pdf_path)
        return pdf_path
    except RuntimeError:
        return html_path


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args()
    path = build_report(args.live, not args.no_db)
    print(f"Saved {path.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
