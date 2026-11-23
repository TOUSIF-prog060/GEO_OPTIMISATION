"""Run the sandbox evaluation and write a report to reports/evals/.

python -m evals.run                 offline suites only (free, no network, no database)
python -m evals.run --live          + live model stability test (real, billed calls)
python -m evals.run --live --repeats 3 --prompts RET-001 SER-001 CMP-001
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from typing import Any

from evals.agent_eval import eval_agent
from evals.gold import GOLD_VERSION
from evals.suites import eval_gaps, eval_measurement, eval_metrics
from src.config import ROOT_DIR

OUT_DIR = ROOT_DIR / "reports" / "evals"


def _f(v: Any, pct: bool = True) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v * 100:.1f}%" if pct else f"{v:.2f}"
    return str(v)


def run(live: bool = False, **live_kw: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "gold_version": GOLD_VERSION,
        "sandbox": "in-memory only: no database writes; offline suites make no network calls",
        "measurement": eval_measurement(),
        "metrics": eval_metrics(),
        "gaps": eval_gaps(),
        "agent": eval_agent(),
    }
    if live:
        from evals.live_model import eval_live

        report["live_model"] = eval_live(**live_kw)
    return report


def to_markdown(r: dict[str, Any]) -> str:
    m = r["measurement"]["metrics"]
    g = r["gaps"]["metrics"]
    a = r["agent"]["metrics"]
    mt = r["metrics"]["metrics"]
    lines = [
        f"# Sandbox evaluation ({r['generated_at']})",
        "",
        f"Gold set `{r['gold_version']}` (synthetic, truth by construction). {r['sandbox']}.",
        "",
        "| Area | Parameter | Result |",
        "|---|---|---|",
        f"| Brand mentions ({m['brand_decisions']} decisions, {m['cases']} answers) | Precision "
        f"| {_f(m['mention']['precision'])} |",
        f"| | Recall | {_f(m['mention']['recall'])} |",
        f"| | F1 | {_f(m['mention']['f1'])} |",
        f"| | Accuracy | {_f(m['mention']['accuracy'])} |",
        f"| List position | Exact match (all mentioned brands) | {_f(m['rank']['exact_match'])} |",
        f"| | Found when truly ranked (n={m['rank']['n_ranked']}) | "
        f"{_f(m['rank']['ranked_found'])} |",
        f"| | Exact when truly ranked | {_f(m['rank']['ranked_exact'])} |",
        f"| | Mean absolute error (positions) | {_f(m['rank']['mean_abs_error'], False)} |",
        f"| | Spurious rank when not ranked (n={m['rank']['n_unranked']}) | "
        f"{_f(m['rank']['spurious_rank_rate'])} |",
        f"| Citations ({m['citations']['n']} URLs) | Domain parsed correctly | "
        f"{_f(m['citations']['domain_accuracy'])} |",
        f"| | Owner brand correct | {_f(m['citations']['owner_accuracy'])} |",
        f"| Metric calculation | Checks correct | {mt['correct']}/{mt['checks']} |",
        f"| Gap detection ({g['scenarios']} scenarios) | Precision | {_f(g['precision'])} |",
        f"| | Recall | {_f(g['recall'])} |",
        f"| | Scenarios fully correct | {g['scenarios_correct']}/{g['scenarios']} |",
        f"| Agent ({a['scenarios']} scenarios) | Pass rate | {_f(a['pass_rate'])} |",
        f"| | Mean run time (s) | {a['mean_seconds']} |",
    ]
    if "live_model" in r:
        lm = r["live_model"]
        if lm.get("skipped"):
            lines.append(f"| Live model | Skipped | {lm['skipped']} |")
        else:
            x = lm["metrics"]
            agree = ", ".join(f"{b} {_f(v)}" for b, v in x["mention_agreement"].items())
            if not x["stability_reported"]:
                lines.append(
                    f"| Live model | Stability not reported | only {x['prompts_with_repeats']} "
                    "question(s) had 2+ successful repeats; see failures |"
                )
            lines += [
                f"| Live model ({x['provider']} {x['model']}, {x['calls']} calls) | "
                f"Success rate | {_f(x['success_rate'])} |",
                f"| | Latency median / p95 (ms) | {x['latency_ms']['median']} / "
                f"{x['latency_ms']['p95']} |",
                f"| | Sources per answer | {x['sources_per_answer']} |",
                f"| | Target mention rate | {_f(x['target_mention_rate'])} |",
                f"| | Mention agreement across repeats | {agree} |",
                f"| | List position stable across repeats | {_f(x['rank_stability'])} |",
                f"| | Cited-source overlap (Jaccard) | {_f(x['source_overlap_jaccard'], False)} |",
            ]
    lines += ["", "## What went wrong", ""]
    for area in ("measurement", "metrics", "gaps", "agent"):
        fails = r[area]["failures"]
        lines.append(f"### {area} ({len(fails)})")
        lines += [f"- `{json.dumps(f, default=str)}`" for f in fails[:40]] or ["- none"]
        lines.append("")
    if r.get("live_model", {}).get("failures"):
        lines.append(f"### live_model ({len(r['live_model']['failures'])})")
        lines += [f"- `{json.dumps(f, default=str)}`" for f in r["live_model"]["failures"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true", help="also run the billed live model test")
    ap.add_argument("--provider", default="gemini")
    ap.add_argument("--prompts", nargs="*", default=None)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()

    kw = {"provider": args.provider, "prompt_ids": args.prompts, "repeats": args.repeats}
    report = run(args.live, **kw)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    json_path = OUT_DIR / f"eval_{stamp}.json"
    md_path = OUT_DIR / f"eval_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md = to_markdown(report)
    md_path.write_text(md, encoding="utf-8")
    print(md)
    print(f"Saved {md_path.relative_to(ROOT_DIR)} and {json_path.name}")


if __name__ == "__main__":
    main()
