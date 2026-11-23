"""Run the discovery engine from the command line.

Examples:
  python scripts/run_discovery.py --panel v0 --dry-run          # no API or DB calls
  python scripts/run_discovery.py --panel v0 --limit 5          # small real test run
  python scripts/run_discovery.py --panel v0 --repeats 3        # full baseline
  python scripts/run_discovery.py --panel v0 --providers perplexity
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
from src.discovery import DiscoveryInput, plan_discovery, run_discovery  # noqa: E402
from src.discovery.panel import load_panel, panel_path, sync_brands, sync_prompts  # noqa: E402
from src.discovery.repository import PostgresRunRepository  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--panel", default="v0", help="panel version (data/reference/prompt_panel_<v>.csv)"
    )
    ap.add_argument("--providers", nargs="*", help="subset of providers (default: all enabled)")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--limit", type=int, help="only the first N prompts")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--run-type", default="baseline", choices=["baseline", "retest", "adhoc"])
    ap.add_argument("--notes")
    ap.add_argument("--dry-run", action="store_true", help="show the plan; call nothing")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    settings = get_settings()
    inp = DiscoveryInput(
        panel_version=args.panel,
        providers=args.providers or None,
        repeats=args.repeats,
        limit=args.limit,
        max_workers=args.workers,
        run_type=args.run_type,
        notes=args.notes,
    )

    plan = plan_discovery(inp, settings)
    print(
        f"Plan: {plan.n_prompts} prompts x {plan.providers} x {plan.repeats} repeats "
        f"= {plan.n_calls} API calls"
    )
    if plan.missing_keys:
        print(f"Missing API keys: {plan.missing_keys} (add them to .env)")
    if args.dry_run:
        return 0
    if plan.missing_keys:
        return 2

    with get_conn() as conn:
        sync_brands(conn, settings.project)
        sync_prompts(conn, load_panel(panel_path(args.panel)), args.panel)
        out = run_discovery(
            inp,
            settings,
            PostgresRunRepository(conn),
            on_progress=lambda p, d, n: print(f"  {p}: {d}/{n}", end="\r"),
        )
    print()
    for r in out.runs:
        cost = f"${r.cost_usd:.4f}" if r.cost_usd is not None else "n/a (prices not set)"
        print(f"{r.provider:<12} {r.status:<10} ok={r.n_ok} failed={r.n_failed} cost={cost}")
        print(f"  run_id={r.run_id}")
    return 0 if all(r.status == "completed" for r in out.runs) else 1


if __name__ == "__main__":
    sys.exit(main())
