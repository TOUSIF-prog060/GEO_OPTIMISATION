"""Run the autonomous GEO agent (LangGraph). Checkpoints are stored in Supabase.

python scripts/run_agent.py start --panel v0 --limit 5 --max-drafts 2     # billed API calls
python scripts/run_agent.py start --run-ids <uuid> <uuid>                 # reuse existing runs
python scripts/run_agent.py status --thread <thread_id>
python scripts/run_agent.py resume --thread <id> --approve <variant_id> --reviewer TS
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agent import get_run, postgres_checkpointer, resume_run, start_run  # noqa: E402
from src.agent.tools import PostgresAgentTools  # noqa: E402
from src.config import get_settings  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--panel", default="v0")
    s.add_argument("--providers", nargs="*")
    s.add_argument("--repeats", type=int, default=1)
    s.add_argument("--limit", type=int)
    s.add_argument("--max-drafts", type=int, default=3)
    s.add_argument("--run-ids", nargs="*", help="skip discovery and use these runs")
    s.add_argument("--sentiment", action="store_true", help="LLM sentiment labels")
    s.add_argument("--accuracy", action="store_true", help="LLM fact checks")
    st = sub.add_parser("status")
    st.add_argument("--thread", required=True)
    r = sub.add_parser("resume")
    r.add_argument("--thread", required=True)
    r.add_argument("--approve", nargs="*", default=[])
    r.add_argument("--reject", nargs="*", default=[])
    r.add_argument("--reviewer", required=True)
    r.add_argument("--notes", default="")
    return ap.parse_args(argv)


def show(status: str, pending: list, values: dict) -> None:
    print(f"status: {status}")
    for d in pending[0]["drafts"] if pending else []:
        print(f"  draft {d['variant_id']}  grounded={d['grounded']}  {d['title']}")
    if values.get("report"):
        print(f"report: {json.dumps(values['report'])}")
    for e in values.get("errors", []):
        print(f"  error: {e}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    tools = PostgresAgentTools()
    with postgres_checkpointer(get_settings().require("supabase_db_url")) as cp:
        if args.cmd == "start":
            params = {"panel_version": args.panel, "providers": args.providers or None,
                      "repeats": args.repeats, "limit": args.limit, "max_drafts": args.max_drafts,
                      "label_sentiment": args.sentiment,
                      "check_accuracy": args.accuracy}  # fmt: skip
            if args.run_ids:
                params["run_ids"] = args.run_ids
            tid, status, pending, values = start_run(tools, cp, params)
            print(f"thread: {tid}")
            show(status, pending, values)
        elif args.cmd == "status":
            show(*get_run(tools, cp, args.thread))
        else:
            decision = {"approved": args.approve, "rejected": args.reject,
                        "reviewer": args.reviewer, "notes": args.notes}  # fmt: skip
            show(*resume_run(tools, cp, args.thread, decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
