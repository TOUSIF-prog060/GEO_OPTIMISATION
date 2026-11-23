"""Human validation of the diagnostics parser (charter D4/D5 evidence).

1) Draw a sample and write one labelling sheet per labeller:
   python scripts/validation.py sample --latest --n 100 --version s1 --labellers TS AB
   -> data/processed/validation/validation_s1_TS.csv, validation_s1_AB.csv
2) Each labeller fills mentioned / rank_in_list / sentiment / is_recommended (yes/no, 1..n, ...).
3) Import the filled sheets:
   python scripts/validation.py import --version s1 --labeller TS --file <path>
4) Evaluate the system against the human labels:
   python scripts/validation.py evaluate --version s1
   -> prints the report and saves reports/evaluation/validation_s1.json
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import get_conn  # noqa: E402
from src.diagnostics.repository import PostgresDiagnosticsRepository, list_runs  # noqa: E402
from src.diagnostics.validation import (  # noqa: E402
    draw_sample,
    evaluate,
    load_labels,
    load_system_mentions,
    read_sheet,
    sample_exists,
    save_labels,
    save_sample,
    write_sheet,
)

SHEET_DIR = ROOT / "data" / "processed" / "validation"
REPORT_DIR = ROOT / "reports" / "evaluation"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sample", help="draw a sample and write labelling sheets")
    which = s.add_mutually_exclusive_group(required=True)
    which.add_argument("--run-id")
    which.add_argument("--latest", action="store_true")
    s.add_argument("--n", type=int, default=100, help="number of answers")
    s.add_argument("--version", required=True, help="sample version, e.g. s1")
    s.add_argument("--labellers", nargs="+", required=True, help="initials, e.g. TS AB")
    s.add_argument("--seed", type=int, default=42)

    i = sub.add_parser("import", help="import one filled labelling sheet")
    i.add_argument("--version", required=True)
    i.add_argument("--labeller", required=True)
    i.add_argument("--file", type=Path, required=True)

    e = sub.add_parser("evaluate", help="compare system output with human labels")
    e.add_argument("--version", required=True)
    return ap.parse_args(argv)


def cmd_sample(args: argparse.Namespace) -> int:
    with get_conn() as conn:
        if sample_exists(conn, args.version):
            print(f"Sample {args.version} already exists. Use a new --version.")
            return 2
        run_id = args.run_id or (list_runs(conn, limit=1) or [{}])[0].get("run_id")
        if not run_id:
            print("No discovery runs yet.")
            return 2
        repo = PostgresDiagnosticsRepository(conn)
        sample = draw_sample(repo.load_responses(run_id), args.n, args.seed)
        save_sample(conn, args.version, sample)
        brands = repo.load_brands()
    for who in args.labellers:
        path = SHEET_DIR / f"validation_{args.version}_{who}.csv"
        n = write_sheet(path, args.version, sample, brands)
        print(f"{who}: {n} rows -> {path.relative_to(ROOT)}")
    print(f"Sampled {len(sample)} answers from run {run_id} (seed {args.seed}).")
    print("Label each sheet independently. Do not look at each other's answers.")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    labels = read_sheet(args.file, args.labeller)
    wrong = {lab.sample_version for lab in labels} - {args.version}
    if wrong:
        print(f"Sheet belongs to sample {sorted(wrong)}, not {args.version}.")
        return 2
    with get_conn() as conn:
        brand_ids = {b.name: b.brand_id for b in PostgresDiagnosticsRepository(conn).load_brands()}
        n = save_labels(conn, labels, brand_ids)
    print(f"Imported {n} labels from {args.labeller}.")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    with get_conn() as conn:
        labels = load_labels(conn, args.version)
        system = load_system_mentions(conn, args.version)
        brand_ids = {b.name: b.brand_id for b in PostgresDiagnosticsRepository(conn).load_brands()}
    if not labels:
        print(f"No labels imported for sample {args.version}.")
        return 2
    report = evaluate(args.version, labels, system, brand_ids)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"validation_{args.version}.json"
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    m = report.mentioned
    print(f"Labellers: {report.labellers} · items: {report.n_items} · "
          f"disagreements: {report.n_disagreements}")  # fmt: skip
    print(
        f"Kappa (mentioned): {report.kappa_mentioned} · kappa (sentiment): {report.kappa_sentiment}"
    )
    print(f"Mention detection: precision {m.precision} recall {m.recall} F1 {m.f1} (n={m.n})")
    print(f"Rank accuracy: {report.rank_accuracy} (n={report.rank_n})")
    print(f"Sentiment: accuracy {report.sentiment_accuracy} macro-F1 {report.sentiment_macro_f1} "
          f"(n={report.sentiment_n})")  # fmt: skip
    print(f"Saved {out.relative_to(ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    return {"sample": cmd_sample, "import": cmd_import, "evaluate": cmd_evaluate}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
