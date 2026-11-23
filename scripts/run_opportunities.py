"""Find ranked opportunities for a diagnosed run (no API calls).

python scripts/run_opportunities.py --latest
python scripts/run_opportunities.py --run-id <uuid>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import get_conn  # noqa: E402
from src.diagnostics.repository import list_runs  # noqa: E402
from src.opportunities import OpportunityInput, find_opportunities  # noqa: E402
from src.opportunities.repository import (  # noqa: E402
    PostgresOpportunityRepository,
    list_opportunities,
)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--run-id")
    which.add_argument("--latest", action="store_true")
    args = ap.parse_args(argv)
    with get_conn() as conn:
        run_id = args.run_id or (list_runs(conn, limit=1) or [{}])[0].get("run_id")
        if not run_id:
            print("No discovery runs yet.")
            return 2
        out = find_opportunities(
            OpportunityInput(run_id=run_id), PostgresOpportunityRepository(conn)
        )
        print(f"{out.n_opportunities} opportunities: {out.by_type}")
        for o in list_opportunities(conn, run_id)[:10]:
            print(
                f"  [{o['priority_score']:>6.1f}] {o['title']}  (effort {o['effort']}, "
                f"confidence {o['confidence']:.2f}, {o['n_evidence']} evidence)"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
