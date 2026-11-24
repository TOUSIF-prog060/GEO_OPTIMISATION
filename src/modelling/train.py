"""Baseline, M1 (L2 logistic) and M2 (random forest, gradient boosting check) for
"is the brand named?", compared on question-grouped cross-validation (charter §11).

    python -m src.modelling.train --workbook path/to/FINAL_Data.xlsx [--no-mlflow]
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import warnings
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import joblib
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold

from src.common.stats import wilson_ci
from src.config import ROOT_DIR, get_settings
from src.modelling.card import write_card
from src.modelling.dataset import build_features, design_matrix, freeze_workbook, read_final_data
from src.modelling.models import (
    CellRate,
    DatasetInfo,
    FactorRate,
    FoldScore,
    Importance,
    ModelSummary,
    OddsRatio,
    RepeatScore,
    TrainInput,
    TrainOutput,
)

log = logging.getLogger(__name__)

BASELINE = "Baseline (rate per engine x question type)"
M1 = "M1 logistic regression (L2)"
M2_RF = "M2 random forest"
M2_GB = "M2 gradient boosting (check)"
SIMPLICITY_ORDER = [BASELINE, M1, M2_RF, M2_GB]
BASELINE_KEYS = ("engine", "question_type")


class InsufficientDataError(ValueError):
    """Too few positives for the number of factors (about 10 per factor)."""


M1_CS = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0)
INNER_SPLITS = 3


def make_estimators(seed: int) -> dict[str, Any]:
    return {
        M1: LogisticRegression(C=1.0, max_iter=5000),
        M2_RF: RandomForestClassifier(
            n_estimators=300, min_samples_leaf=5, random_state=seed, n_jobs=-1
        ),
        M2_GB: HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.05, max_iter=200, random_state=seed
        ),
    }


def baseline_predict(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Training rate of the test row's engine x question type cell; falls back to the
    engine rate, then the overall rate, when the cell is absent from training."""
    overall = float(train["y"].mean())
    cell = train.groupby(list(BASELINE_KEYS))["y"].mean().to_dict()
    engine = train.groupby("engine")["y"].mean().to_dict()
    out = []
    for e, q in zip(test["engine"], test["question_type"], strict=True):
        out.append(cell.get((e, q), engine.get(e, overall)))
    return np.asarray(out, dtype=float)


def best_threshold(y: np.ndarray, p: np.ndarray) -> float:
    """Probability cut-off with the highest F1 on the given predictions."""
    best_t, best_f1 = 0.5, -1.0
    for t in np.unique(p):
        f1 = f1_score(y, (p >= t).astype(int), zero_division=0)
        if f1 > best_f1:
            best_t, best_f1 = float(t), f1
    return best_t


def inner_splits(groups: np.ndarray, n: int = INNER_SPLITS) -> list[tuple[np.ndarray, np.ndarray]]:
    """Grouped splits inside a training set, for tuning and thresholds (never sees the test)."""
    k = min(n, len(set(groups)))
    if k < 2:
        return []
    return list(GroupKFold(n_splits=k).split(np.zeros(len(groups)), groups=groups))


def tune_m1_c(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray) -> float:
    """L2 strength with the best inner grouped-CV PR-AUC; 1.0 if it cannot be tuned."""
    splits = [s for s in inner_splits(groups) if 0 < y[s[1]].sum() < len(s[1])]
    best_c, best = 1.0, -1.0
    for c in M1_CS:
        aps = []
        for tr, te in splits:
            if y[tr].min() == y[tr].max():
                continue
            m = LogisticRegression(C=c, max_iter=5000).fit(X.iloc[tr], y[tr])
            aps.append(average_precision_score(y[te], m.predict_proba(X.iloc[te])[:, 1]))
        if aps and float(np.mean(aps)) > best:
            best_c, best = c, float(np.mean(aps))
    return best_c


def fit_predict(
    name: str,
    est: Any,
    table: pd.DataFrame,
    X: pd.DataFrame,
    tr: np.ndarray,
    te: np.ndarray,
    groups: np.ndarray,
) -> np.ndarray:
    """Fit one model on rows tr (tuning only inside tr) and predict rows te."""
    if name == BASELINE:
        return baseline_predict(table.iloc[tr], table.iloc[te])
    y = table["y"].to_numpy()
    model = clone(est)
    if name == M1:
        model.set_params(C=tune_m1_c(X.iloc[tr], y[tr], groups[tr]))
    model.fit(X.iloc[tr], y[tr])
    return model.predict_proba(X.iloc[te])[:, 1]


def inner_threshold(
    name: str, est: Any, table: pd.DataFrame, X: pd.DataFrame, tr: np.ndarray, groups: np.ndarray
) -> float:
    """F1-best cut-off chosen on inner out-of-fold predictions of the training rows, so a model
    that memorises its training data does not get an over-high cut-off."""
    y = table["y"].to_numpy()
    oof = np.full(len(tr), np.nan)
    for itr, ite in inner_splits(groups[tr]):
        if y[tr][itr].min() == y[tr][itr].max():
            continue
        oof[ite] = fit_predict(name, est, table, X, tr[itr], tr[ite], groups)
    ok = ~np.isnan(oof)
    return best_threshold(y[tr][ok], oof[ok]) if ok.any() else 0.5


def score(
    model: str, fold: int, y: np.ndarray, p: np.ndarray, threshold: float, repeat: int = 1
) -> FoldScore:
    has_pos = bool(y.sum()) and bool((1 - y).sum())
    return FoldScore(
        model=model,
        repeat=repeat,
        fold=fold,
        n_test=len(y),
        n_pos_test=int(y.sum()),
        pr_auc=float(average_precision_score(y, p)) if has_pos else None,
        f1=float(f1_score(y, (p >= threshold).astype(int), zero_division=0)),
        brier=float(brier_score_loss(y, p)),
        threshold=threshold,
    )


def cross_validate(
    table: pd.DataFrame, X: pd.DataFrame, n_splits: int, seed: int, n_repeats: int = 1
) -> tuple[list[FoldScore], list[RepeatScore]]:
    """Grouped CV repeated with reshuffled folds. Every model sees the same folds; each run is
    scored on its pooled out-of-fold predictions, which is steadier than averaging small folds."""
    y = table["y"].to_numpy()
    groups = table["group_id"].to_numpy()
    if len(set(groups)) < n_splits:
        raise InsufficientDataError(
            f"Only {len(set(groups))} question groups; need at least {n_splits} "
            f"for {n_splits} folds"
        )
    estimators: dict[str, Any] = {BASELINE: None, **make_estimators(seed)}
    folds: list[FoldScore] = []
    runs: list[RepeatScore] = []
    for r in range(1, n_repeats + 1):
        cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed + r - 1)
        oof = {name: np.zeros(len(y)) for name in estimators}
        hits = {name: np.zeros(len(y), dtype=int) for name in estimators}
        for fold, (tr, te) in enumerate(cv.split(X, y, groups), start=1):
            for name, est in estimators.items():
                p_te = fit_predict(name, est, table, X, tr, te, groups)
                t = inner_threshold(name, est, table, X, tr, groups)
                oof[name][te] = p_te
                hits[name][te] = (p_te >= t).astype(int)
                folds.append(score(name, fold, y[te], p_te, t, repeat=r))
        for name in estimators:
            runs.append(
                RepeatScore(
                    model=name,
                    repeat=r,
                    pr_auc=float(average_precision_score(y, oof[name])),
                    brier=float(brier_score_loss(y, oof[name])),
                    f1=float(f1_score(y, hits[name], zero_division=0)),
                )
            )
    return folds, runs


def summarise(scores: list[FoldScore], runs: list[RepeatScore] | None = None) -> list[ModelSummary]:
    """Per-model summary. With CV runs: mean and sd over runs of pooled PR-AUC, plus how many
    runs beat the baseline on the same folds. Without: mean over folds."""
    out = []
    base_by_run = {r.repeat: r.pr_auc for r in runs or [] if r.model == BASELINE}
    for name in SIMPLICITY_ORDER:
        rows = [s for s in scores if s.model == name]
        mine = [r for r in runs or [] if r.model == name]
        if mine:
            aucs = [r.pr_auc for r in mine]
            wins = sum(r.pr_auc > base_by_run.get(r.repeat, np.inf) for r in mine)
            out.append(
                ModelSummary(
                    model=name,
                    pr_auc_mean=float(np.mean(aucs)),
                    pr_auc_sd=float(np.std(aucs, ddof=1)) if len(aucs) > 1 else 0.0,
                    f1_mean=float(np.mean([r.f1 for r in mine])),
                    brier_mean=float(np.mean([r.brier for r in mine])),
                    n_folds=len(rows),
                    n_runs=len(mine),
                    wins_vs_baseline=None if name == BASELINE else int(wins),
                )
            )
        elif rows:
            aucs = [s.pr_auc for s in rows if s.pr_auc is not None]
            out.append(
                ModelSummary(
                    model=name,
                    pr_auc_mean=float(np.mean(aucs)) if aucs else None,
                    pr_auc_sd=float(np.std(aucs, ddof=1)) if len(aucs) > 1 else None,
                    f1_mean=float(np.mean([s.f1 for s in rows])),
                    brier_mean=float(np.mean([s.brier for s in rows])),
                    n_folds=len(rows),
                )
            )
    return out


def choose_model(summary: list[ModelSummary]) -> tuple[str, str]:
    """Simplest model that beats the baseline's PR-AUC and is within one standard error of the
    best model (one-standard-error rule). With CV runs it must also beat the baseline in more
    than half the runs on the same folds. Baseline if nothing qualifies."""
    by = {s.model: s for s in summary if s.pr_auc_mean is not None}
    if BASELINE not in by:
        return BASELINE, "Baseline kept: PR-AUC could not be computed."
    base = by[BASELINE].pr_auc_mean
    best = max(by.values(), key=lambda s: s.pr_auc_mean or 0.0)
    se = (best.pr_auc_sd or 0.0) / math.sqrt(best.n_runs or best.n_folds)
    for name in SIMPLICITY_ORDER[1:]:
        s = by.get(name)
        if not s or s.pr_auc_mean <= base or s.pr_auc_mean < best.pr_auc_mean - se:
            continue
        if s.wins_vs_baseline is not None and s.wins_vs_baseline * 2 <= s.n_runs:
            continue
        wins = ""
        if s.wins_vs_baseline is not None:
            wins = f", winning {s.wins_vs_baseline} of {s.n_runs} runs"
        return name, (
            f"{name} is the simplest model that beats the baseline "
            f"(PR-AUC {s.pr_auc_mean:.3f} vs {base:.3f}{wins}) and is within one standard "
            f"error of the best ({best.model}, {best.pr_auc_mean:.3f} ± {se:.3f})."
        )
    return BASELINE, (
        f"No model beat the baseline's PR-AUC ({base:.3f}) reliably on unseen questions; "
        "the baseline is kept."
    )


def odds_ratios(table: pd.DataFrame, X: pd.DataFrame, warn: list[str]) -> list[OddsRatio]:
    """Unpenalised logistic fit with standard errors clustered by question group, so repeated
    answers to one question are not counted as independent. Association, not cause."""
    exog = sm.add_constant(X.astype(float), has_constant="add")
    groups = pd.factorize(table["group_id"])[0]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            res = sm.GLM(table["y"].astype(float), exog, family=sm.families.Binomial()).fit(
                cov_type="cluster", cov_kwds={"groups": groups}
            )
        except Exception as exc:  # separation or singular matrix: report, don't crash
            log.exception("Odds-ratio fit failed")
            warn.append(f"Odds ratios not computed: {exc}")
            return []
    for w in caught:
        msg = str(w.message).splitlines()[0]
        if "separation" in msg.lower() or "converge" in msg.lower():
            warn.append(f"Odds-ratio fit: {msg}")
    ci = res.conf_int()
    out = []
    for term in X.columns:
        out.append(
            OddsRatio(
                term=term,
                odds_ratio=float(np.exp(res.params[term])),
                ci_low=float(np.exp(ci.loc[term, 0])),
                ci_high=float(np.exp(ci.loc[term, 1])),
                p_value=float(res.pvalues[term]),
            )
        )
    return out


def factor_importance(
    table: pd.DataFrame,
    X: pd.DataFrame,
    groups: dict[str, list[str]],
    n_splits: int,
    n_repeats: int,
    seed: int,
    make: Callable[[], Any],
) -> list[Importance]:
    """Drop in held-out PR-AUC when all columns of one factor are shuffled together."""
    y = table["y"].to_numpy()
    rng = np.random.default_rng(seed)
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    drops: dict[str, list[float]] = {f: [] for f, cols in groups.items() if cols}
    for tr, te in cv.split(X, y, table["group_id"]):
        if not y[te].sum() or y[te].all():
            continue
        m = make().fit(X.iloc[tr], y[tr])
        Xte = X.iloc[te]
        base = average_precision_score(y[te], m.predict_proba(Xte)[:, 1])
        for f in drops:
            for _ in range(n_repeats):
                shuffled = Xte.copy()
                order = rng.permutation(len(Xte))
                shuffled[groups[f]] = Xte[groups[f]].to_numpy()[order]
                p = m.predict_proba(shuffled)[:, 1]
                drops[f].append(base - average_precision_score(y[te], p))
    out = [
        Importance(factor=f, pr_auc_drop=float(np.mean(v)), sd=float(np.std(v)))
        for f, v in drops.items()
        if v
    ]
    return sorted(out, key=lambda i: i.pr_auc_drop, reverse=True)


def baseline_cells(table: pd.DataFrame) -> list[CellRate]:
    out = []
    for (e, q), g in table.groupby(list(BASELINE_KEYS)):
        n, x = len(g), int(g["y"].sum())
        ci = wilson_ci(x, n)
        out.append(
            CellRate(
                engine=e,
                question_type=q,
                n=n,
                positives=x,
                rate=x / n,
                ci_low=ci[0] if ci else None,
                ci_high=ci[1] if ci else None,
            )
        )
    return out


def factor_rates(table: pd.DataFrame, factors: list[str]) -> list[FactorRate]:
    """Share of answers naming the brand for every level of every factor, with Wilson 95%."""
    out = []
    for f in factors:
        for level, g in table.groupby(f):
            n, x = len(g), int(g["y"].sum())
            ci = wilson_ci(x, n)
            out.append(
                FactorRate(
                    factor=f,
                    level=str(level),
                    n=n,
                    positives=x,
                    rate=x / n,
                    ci_low=ci[0] if ci else None,
                    ci_high=ci[1] if ci else None,
                )
            )
    return out


def check_size(n_pos: int, n_neg: int, n_factors: int, n_cols: int, inp: TrainInput) -> list[str]:
    need = inp.min_positives_per_factor * n_factors
    events = min(n_pos, n_neg)
    if events < need:
        raise InsufficientDataError(
            f"{events} answers in the smaller class; {need} needed for {n_factors} factors "
            f"({inp.min_positives_per_factor} per factor). "
            "Collect more answers or use fewer factors."
        )
    warn = []
    if n_cols and events / n_cols < 10:
        warn.append(
            f"{events / n_cols:.1f} events per model column (below 10): L2 regularisation keeps "
            "M1 stable, but read single odds ratios with care."
        )
    return warn


def thin_levels(table: pd.DataFrame, factors: list[str]) -> list[str]:
    """Factor levels found in only one question group. When that question is held out the
    models have never seen the level, so its effect cannot be checked on new questions."""
    out = []
    for f in factors:
        n_groups = table.groupby(f)["group_id"].nunique()
        for level, k in n_groups.items():
            if k < 2:
                out.append(
                    f"{f}={level} comes from a single question group; its effect rests on that "
                    "one question and cannot be cross-validated."
                )
    return out


def run_training(inp: TrainInput) -> TrainOutput:
    settings = get_settings()
    brands = [settings.project.target, *settings.project.competitors]
    target = inp.target_brand or settings.project.target.name
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    frozen, sha = freeze_workbook(inp.workbook, inp.raw_dir or ROOT_DIR / "data/raw/collected")
    raw = read_final_data(frozen)
    table, excluded, agreement = build_features(raw, brands, target, inp.factors, inp.strict)
    snap_dir = inp.snapshot_dir or ROOT_DIR / "data/processed/modelling"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snap_dir / f"features_{sha[:10]}{'_strict' if inp.strict else ''}.csv"
    table.to_csv(snapshot, index=False)

    X, refs, dropped, groups = design_matrix(table, inp.factors)
    n_pos = int(table["y"].sum())
    warn = check_size(n_pos, len(table) - n_pos, len(inp.factors), X.shape[1], inp)
    warn += thin_levels(table, inp.factors)

    scores, runs = cross_validate(table, X, inp.n_splits, inp.seed, inp.n_cv_repeats)
    summary = summarise(scores, runs)
    m1_c = tune_m1_c(X, table["y"].to_numpy(), table["group_id"].to_numpy())
    chosen, reason = choose_model(summary)
    ors = odds_ratios(table, X, warn)
    est = make_estimators(inp.seed)
    imp = factor_importance(
        table, X, groups, inp.n_splits, inp.n_repeats_importance, inp.seed,
        lambda: clone(est[M2_RF]),
    )  # fmt: skip

    out_dir = inp.out_dir or ROOT_DIR / "reports/models" / f"{stamp}_{sha[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = TrainOutput(
        dataset=DatasetInfo(
            source_file=str(inp.workbook),
            frozen_copy=str(frozen),
            sha256=sha,
            snapshot=str(snapshot),
            target=target,
            analysis_set="use_strict" if inp.strict else "use_in_model",
            n_rows=len(raw),
            n_used=len(table),
            n_positive=n_pos,
            excluded=excluded,
            reader_vs_sheet_agreement=agreement,
            n_groups=int(table["group_id"].nunique()),
        ),
        factors=inp.factors,
        reference_levels=refs,
        dropped_columns=dropped,
        n_columns=X.shape[1],
        positives_per_factor=n_pos / len(inp.factors),
        positives_per_column=n_pos / max(X.shape[1], 1),
        warnings=warn,
        folds=scores,
        repeats=runs,
        summary=summary,
        m1_c=m1_c,
        prevalence=n_pos / len(table),
        factor_rates=factor_rates(table, inp.factors),
        chosen=chosen,
        choice_reason=reason,
        odds_ratios=ors,
        importances=imp,
        baseline_cells=baseline_cells(table),
        out_dir=str(out_dir),
    )

    # Artefacts: fitted models on all data, tables, the model card.
    est[M1].set_params(C=m1_c)
    final = {name: clone(e).fit(X, table["y"]) for name, e in est.items()}
    joblib.dump({"models": final, "columns": list(X.columns), "factors": inp.factors,
                 "reference_levels": refs, "chosen": chosen, "data_sha256": sha},
                out_dir / "models.joblib")  # fmt: skip
    pd.DataFrame([s.model_dump() for s in scores]).to_csv(out_dir / "fold_scores.csv", index=False)
    pd.DataFrame([r.model_dump() for r in runs]).to_csv(out_dir / "cv_runs.csv", index=False)
    pd.DataFrame([o.model_dump() for o in ors]).to_csv(out_dir / "odds_ratios.csv", index=False)
    write_card(output, out_dir / "model_card.md")

    if inp.track:
        from src.modelling.tracking import log_run

        output.mlflow_run_id = log_run(output, inp, out_dir)
    (out_dir / "result.json").write_text(output.model_dump_json(indent=2), encoding="utf-8")
    return output


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--data",
        "--workbook",
        dest="workbook",
        required=True,
        help="clean data-v1.0 CSV (preferred) or the raw collection workbook",
    )
    p.add_argument("--strict", action="store_true", help="use only use_strict rows")
    p.add_argument("--target", default=None)
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--repeats", type=int, default=10, help="reshuffled grouped CV runs")
    p.add_argument("--no-mlflow", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    from pathlib import Path

    out = run_training(
        TrainInput(
            workbook=Path(a.workbook),
            target_brand=a.target,
            n_splits=a.folds,
            n_cv_repeats=a.repeats,
            seed=a.seed,
            track=not a.no_mlflow,
            strict=a.strict,
        )  # fmt: skip
    )
    print(json.dumps({"chosen": out.chosen, "out_dir": out.out_dir,
                      "mlflow_run_id": out.mlflow_run_id,
                      "summary": [s.model_dump() for s in out.summary]}, indent=2))  # fmt: skip


if __name__ == "__main__":
    main()
