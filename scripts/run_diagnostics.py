"""Run diagnostics on a discovery run: parse answers, compute visibility metrics.

Examples:
  python scripts/run_diagnostics.py --latest                 # newest run, no API calls
  python scripts/run_diagnostics.py --run-id <uuid>
  python scripts/run_diagnostics.py --latest --classify      # + LLM sentiment labels (billed)
  python scripts/run_diagnostics.py --latest --accuracy      # + LLM fact checks (billed)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402
from src.db import get_conn  # noqa: E402
from src.diagnostics import (  # noqa: E402
    AccuracyInput,
    ClassifyInput,
    DiagnoseInput,
    check_accuracy,
    classify_mentions,
    diagnose,
)
from src.diagnostics.repository import (  # noqa: E402
    PostgresDiagnosticsRepository,
    list_runs,
    load_gold_accuracy,
    load_repeatability,
    load_visibility,
    sync_reference,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--run-id")
    which.add_argument("--latest", action="store_true", help="newest discovery run")
    ap.add_argument("--ref", default="v1", help="reference data version (domains/products/facts)")
    ap.add_argument("--classify", action="store_true", help="LLM sentiment labels (OpenAI key)")
    ap.add_argument("--accuracy", action="store_true", help="LLM fact checks (OpenAI key)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    settings = get_settings()
    with get_conn() as conn:
        print(f"Reference data synced: {sync_reference(conn, args.ref)}")
        run_id = args.run_id
        if args.latest:
            runs = list_runs(conn, limit=1)
            if not runs:
                print("No discovery runs yet. Run scripts/run_discovery.py first.")
                return 2
            run_id = runs[0]["run_id"]
        repo = PostgresDiagnosticsRepository(conn)
        out = diagnose(DiagnoseInput(run_id=run_id), repo)
        print(out.model_dump_json(indent=2))
        if args.classify:
            res = classify_mentions(ClassifyInput(run_id=run_id), settings, repo)
            print(f"Labelled {res.n_classified} mentions ({res.n_failed} failed) with {res.model}")
        if args.accuracy:
            acc = check_accuracy(AccuracyInput(run_id=run_id), settings, repo)
            print(f"Accuracy: {acc.n_checks} checks on {acc.n_responses_checked} answers")
            for r in load_gold_accuracy(conn, run_id):
                rate = "-" if r["accuracy_rate"] is None else f"{float(r['accuracy_rate']):.0%}"
                print(
                    f"  {r['subject']} / {r['attribute']}: {rate} "
                    f"(match {r['n_match']}, mismatch {r['n_mismatch']}, "
                    f"not stated {r['n_not_mentioned']}, unverifiable {r['n_unverifiable']})"
                )
        for r in load_repeatability(conn, run_id):
            print(
                f"Repeatability {r['brand']}: agreement {float(r['agreement_rate']):.0%} "
                f"over {r['n_prompts']} repeated prompts"
            )
        print(f"\n{'brand':<16}{'mention':>9}{'SoV':>8}{'rank':>7}{'cite':>8}{'pos':>7}")
        for r in load_visibility(conn, run_id):
            if r["category"] != "ALL":
                continue

            def f(v, pct=True):
                return "-" if v is None else (f"{float(v):.0%}" if pct else f"{float(v):.1f}")

            print(
                f"{r['brand']:<16}{f(r['mention_rate']):>9}{f(r['share_of_voice']):>8}"
                f"{f(r['avg_rank'], False):>7}{f(r['citation_share']):>8}"
                f"{f(r['positive_rate']):>7}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
