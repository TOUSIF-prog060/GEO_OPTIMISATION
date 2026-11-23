"""Experimentation lab.

python scripts/run_experiment.py plan --baseline <run_id> --variant <variant_id> --opportunity <id>
python scripts/run_experiment.py plan --baseline <run_id> --design repeat_baseline   # noise check
python scripts/run_experiment.py retest --experiment <id> --repeats 3               # billed
python scripts/run_experiment.py list
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import services  # noqa: E402
from src.db import get_conn  # noqa: E402
from src.experimentation.repository import list_experiments  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--baseline", required=True)
    p.add_argument("--variant")
    p.add_argument("--opportunity")
    p.add_argument(
        "--design", default="content_variant", choices=["content_variant", "repeat_baseline"]
    )
    r = sub.add_parser("retest")
    r.add_argument("--experiment", required=True)
    r.add_argument("--repeats", type=int, default=3)
    sub.add_parser("list")
    args = ap.parse_args(argv)

    if args.cmd == "plan":
        eid = services.plan_experiment(
            args.variant, args.opportunity, args.baseline, "cli", args.design
        )
        print(f"experiment: {eid}")
    elif args.cmd == "retest":
        out = services.retest(args.experiment, args.repeats)
        for row in out.results:
            print(
                f"brand {row.brand_id}: {row.baseline_value} -> {row.retest_value}  "
                f"{row.interpretation}"
            )
    else:
        with get_conn() as conn:
            for e in list_experiments(conn):
                print(
                    f"{e['experiment_id']}  {e['status']:<8} {e['design']:<16} "
                    f"{e['n_prompts']} prompts"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
