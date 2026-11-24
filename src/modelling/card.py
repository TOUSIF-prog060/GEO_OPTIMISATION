"""Model card (markdown) written next to every training run."""

from __future__ import annotations

from pathlib import Path

from src.modelling.models import TrainOutput


def _pct(x: float | None, d: int = 0) -> str:
    return "–" if x is None else f"{x * 100:.{d}f}%"


def _num(x: float | None, d: int = 3) -> str:
    return "–" if x is None else f"{x:.{d}f}"


def render_card(o: TrainOutput) -> str:
    ds = o.dataset
    lines = [
        f"# Model card: is {ds.target} named?",
        "",
        "## Data",
        f"- Source: `{ds.source_file}` (frozen copy `{ds.frozen_copy}`)",
        f"- SHA-256: `{ds.sha256}`",
        f"- Feature snapshot: `{ds.snapshot}`",
        f"- Analysis set: {ds.analysis_set}",
        f"- Rows in file: {ds.n_rows}; used: {ds.n_used}; {ds.target} named in "
        f"{ds.n_positive} ({_pct(ds.n_positive / ds.n_used if ds.n_used else None, 1)})",
        "- Excluded: " + ", ".join(f"{k}: {v}" for k, v in ds.excluded.items()),
        f"- Question groups (English + Hinglish twins kept together): {ds.n_groups}",
        f"- Our alias reader vs the sheet's word search: {_pct(ds.reader_vs_sheet_agreement, 1)} "
        "agreement",
        "",
        "## Factors",
        "| Factor | Reference level |",
        "|---|---|",
        *[f"| {f} | {o.reference_levels.get(f, '–')} |" for f in o.factors],
        "",
        f"{o.n_columns} model columns; {o.positives_per_factor:.1f} positives per factor, "
        f"{o.positives_per_column:.1f} per column.",
    ]
    if o.dropped_columns:
        lines += ["", "Columns dropped as duplicates of another column:"]
        lines += [f"- `{c}` = `{k}`" for c, k in o.dropped_columns.items()]
    lines += [
        "",
        "## Cross-validated performance",
        "Folds are grouped by question, so no question appears in both training and test. "
        "Grouped CV is repeated with reshuffled folds; each run is scored on its pooled "
        "out-of-fold predictions. Tuning (M1's L2 strength) and F1 cut-offs use inner grouped "
        "splits of the training folds only.",
        "",
        f"Base rate (share of answers naming the brand): {_pct(o.prevalence, 1)}. "
        f"A model that ranks at random scores about this PR-AUC.",
        "",
        "| Model | PR-AUC (mean ± sd over runs) | Runs beating baseline | F1 | Brier |",
        "|---|---|---|---|---|",
    ]
    for s in o.summary:
        wins = "–" if s.wins_vs_baseline is None else f"{s.wins_vs_baseline} of {s.n_runs}"
        lines.append(
            f"| {s.model} | {_num(s.pr_auc_mean)} ± {_num(s.pr_auc_sd)} | {wins} | "
            f"{_num(s.f1_mean)} | {_num(s.brier_mean)} |"
        )
    if o.m1_c is not None:
        lines += ["", f"M1 L2 strength chosen by grouped CV on all data: C = {o.m1_c}."]
    lines += ["", f"**Chosen: {o.chosen}.** {o.choice_reason}", ""]
    lines += [
        "## Odds ratios (association in this sample, not cause)",
        "Unpenalised logistic regression, 95% intervals clustered by question group. "
        "Each ratio compares a level with its factor's reference level.",
        "",
        "| Term | Odds ratio | 95% interval | p |",
        "|---|---|---|---|",
    ]
    for r in sorted(o.odds_ratios, key=lambda r: r.odds_ratio, reverse=True):
        lines.append(
            f"| {r.term} | {r.odds_ratio:.2f} | {r.ci_low:.2f} – {r.ci_high:.2f} | "
            f"{r.p_value:.3f} |"
        )
    lines += [
        "",
        "## Factor importance (M2 random forest)",
        "Drop in held-out PR-AUC when the factor is shuffled.",
        "",
        "| Factor | PR-AUC drop | sd |",
        "|---|---|---|",
        *[f"| {i.factor} | {i.pr_auc_drop:.3f} | {i.sd:.3f} |" for i in o.importances],
        "",
        "## Warnings",
        *([f"- {w}" for w in o.warnings] or ["- None"]),
        "",
        "## Limits",
        "- Observational data: coefficients describe association in this sample, not cause.",
        "- Most answers were collected several questions per chat (`batched_chat`); the "
        "`collection_method` factor measures that effect but cannot remove it.",
        "- The target is found by alias rules (no hand check yet); the human-label sample "
        "measures their accuracy.",
        "- Model version and plan were not recorded for many rows, so they are not factors.",
        "- Accuracy is not reported as a headline: the brand is named in a minority of answers.",
    ]
    return "\n".join(lines) + "\n"


def write_card(o: TrainOutput, path: Path) -> Path:
    path.write_text(render_card(o), encoding="utf-8")
    return path
