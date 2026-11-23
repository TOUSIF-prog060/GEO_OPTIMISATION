"""Visibility models on a synthetic workbook with a planted effect (no network, no real data)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import Brand
from src.modelling import train as T
from src.modelling.dataset import (
    build_features,
    design_matrix,
    freeze_workbook,
    label_brands,
    read_final_data,
)
from src.modelling.models import ModelSummary, TrainInput

BRANDS = [
    Brand(name="Sephora India", is_target=True, aliases=["Sephora", "sephora.in"]),
    Brand(name="Nykaa", is_target=False, aliases=["Nykaa"]),
]
FACTORS = ["engine", "question_type", "category", "language", "collection_method"]


def synthetic_sheet(n_groups: int = 12, repeats: int = 6, seed: int = 0) -> pd.DataFrame:
    """ChatGPT names Sephora far more often than Perplexity; shortlists more than budget."""
    rng = np.random.default_rng(seed)
    rows = []
    qtypes = ["budget", "shortlist", "need"]
    cats = ["sunscreen", "lipstick", "fragrance"]
    i = 0
    for g in range(n_groups):
        for lang, suffix in (("en", "E"), ("hinglish", "H")):
            for engine in ("chatgpt", "perplexity"):
                for r in range(repeats):
                    qt = qtypes[g % 3]
                    p = (0.55 if engine == "chatgpt" else 0.1) + (0.2 if qt == "shortlist" else 0)
                    named = rng.random() < p
                    i += 1
                    rows.append(
                        {
                            "run_id": f"S{i:04d}",
                            "engine": engine,
                            "run_no": r + 1,
                            "prompt_id": f"B{g + 1:02d}{suffix}",
                            "language": lang,
                            "question_type": qt,
                            "category": cats[(g // 3) % 3],
                            "collection_method": "batched_chat" if r % 2 else "single_chat",
                            "full_response_text": "Try Sephora's range." if named else "Try Nykaa.",
                            "sephora_word_in_answer": named,
                            "use_in_model": "yes",
                        }
                    )
    rows.append({**rows[0], "run_id": "S9999", "use_in_model": "no"})
    return pd.DataFrame(rows)


@pytest.fixture
def workbook(tmp_path):
    path = tmp_path / "FINAL_Data.xlsx"
    with pd.ExcelWriter(path) as xw:
        pd.DataFrame({"x": ["instructions"]}).to_excel(xw, sheet_name="Instructions", index=False)
        synthetic_sheet().to_excel(xw, sheet_name="Final_Data", index=False)
    return path


def test_label_brands_uses_aliases_and_word_boundaries():
    texts = pd.Series(["Buy at sephora.in", "Nykaa's offers", "nothing", "Sephoras?"])
    out = label_brands(texts, BRANDS)
    assert out["named_sephora_india"].tolist() == [True, False, False, False]
    assert out["named_nykaa"].tolist() == [False, True, False, False]


def test_freeze_is_unchanged_copy_named_by_checksum(workbook, tmp_path):
    frozen, sha = freeze_workbook(workbook, tmp_path / "raw")
    assert frozen.read_bytes() == workbook.read_bytes()
    assert sha[:10] in frozen.name
    again, _ = freeze_workbook(workbook, tmp_path / "raw")
    assert again == frozen


def test_read_final_data_requires_columns(tmp_path):
    path = tmp_path / "bad.xlsx"
    pd.DataFrame({"run_id": ["S1"]}).to_excel(path, sheet_name="Final_Data", index=False)
    with pytest.raises(ValueError, match="missing columns"):
        read_final_data(path)


def test_build_features_filters_and_groups_twins():
    table, excluded, agreement = build_features(synthetic_sheet(), BRANDS, "Sephora India", FACTORS)
    assert excluded["use_in_model = no"] == 1
    assert "S9999" not in set(table["response_id"])
    assert set(table.loc[table["prompt_id"].isin(["B01E", "B01H"]), "group_id"]) == {"B01"}
    assert agreement == 1.0
    assert table["y"].isin([0, 1]).all()


def test_build_features_unknown_target():
    with pytest.raises(ValueError, match="Unknown target"):
        build_features(synthetic_sheet(), BRANDS, "Tira", FACTORS)


def test_design_matrix_reference_is_most_common_and_duplicates_dropped():
    table = pd.DataFrame(
        {
            "a": ["x", "x", "x", "y", "z"],
            "b": ["p", "p", "p", "q", "p"],  # b=q is identical to a=y
            "group_id": list("abcde"),
        }
    )
    X, refs, dropped, groups = design_matrix(table, ["a", "b"])
    assert refs == {"a": "x", "b": "p"}
    assert list(X.columns) == ["a=y", "a=z"]
    assert dropped == {"b=q": "a=y"}
    assert groups == {"a": ["a=y", "a=z"], "b": []}


def test_baseline_predict_falls_back_to_engine_then_overall():
    train = pd.DataFrame(
        {"engine": ["a", "a", "b"], "question_type": ["s", "s", "s"], "y": [1, 0, 0]}
    )
    test = pd.DataFrame({"engine": ["a", "a", "c"], "question_type": ["s", "n", "s"]})
    assert T.baseline_predict(train, test).tolist() == pytest.approx([0.5, 0.5, 1 / 3])


def test_best_threshold_maximises_f1():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.4, 0.35, 0.8])
    assert T.best_threshold(y, p) == pytest.approx(0.35)


def test_choose_model_prefers_simplest_within_one_se():
    s = [
        ModelSummary(model=T.BASELINE, pr_auc_mean=0.30, pr_auc_sd=0.05, f1_mean=0, brier_mean=0,
                     n_folds=4),
        ModelSummary(model=T.M1, pr_auc_mean=0.48, pr_auc_sd=0.04, f1_mean=0, brier_mean=0,
                     n_folds=4),
        ModelSummary(model=T.M2_RF, pr_auc_mean=0.50, pr_auc_sd=0.06, f1_mean=0, brier_mean=0,
                     n_folds=4),
    ]  # fmt: skip
    assert T.choose_model(s)[0] == T.M1
    s[1] = s[1].model_copy(update={"pr_auc_mean": 0.40})
    assert T.choose_model(s)[0] == T.M2_RF
    s[2] = s[2].model_copy(update={"pr_auc_mean": 0.20})
    s[1] = s[1].model_copy(update={"pr_auc_mean": 0.25})
    assert T.choose_model(s)[0] == T.BASELINE


def test_size_guard_refuses_too_few_positives(tmp_path):
    inp = TrainInput(workbook=tmp_path / "x.xlsx")
    with pytest.raises(T.InsufficientDataError):
        T.check_size(n_pos=40, n_neg=500, n_factors=5, n_cols=10, inp=inp)
    assert T.check_size(n_pos=60, n_neg=500, n_factors=5, n_cols=10, inp=inp)  # warns per column
    assert T.check_size(n_pos=200, n_neg=500, n_factors=5, n_cols=10, inp=inp) == []


def test_thin_levels_flags_single_question_levels():
    table = pd.DataFrame({"qt": ["a", "a", "b", "b"], "group_id": ["g1", "g2", "g3", "g3"]})
    warns = T.thin_levels(table, ["qt"])
    assert len(warns) == 1 and "qt=b" in warns[0]


def test_cross_validation_never_splits_a_question_group():
    table, _, _ = build_features(synthetic_sheet(), BRANDS, "Sephora India", FACTORS)
    X, *_ = design_matrix(table, FACTORS)
    scores = T.cross_validate(table, X, n_splits=4, seed=1)
    assert {s.model for s in scores} == set(T.SIMPLICITY_ORDER)
    assert sum(s.n_test for s in scores if s.model == T.BASELINE) == len(table)


def test_run_training_end_to_end_finds_planted_engine_effect(workbook, tmp_path):
    out = T.run_training(
        TrainInput(
            workbook=workbook,
            n_splits=4,
            n_repeats_importance=2,
            track=False,
            out_dir=tmp_path / "out",
            raw_dir=tmp_path / "raw",
            snapshot_dir=tmp_path / "snap",
        )  # fmt: skip
    )
    ors = {o.term: o for o in out.odds_ratios}
    assert out.reference_levels["engine"] == "chatgpt" or "engine=chatgpt" in ors
    perplexity = ors.get("engine=perplexity")
    assert perplexity is not None and perplexity.ci_high < 1  # planted: Perplexity names it less
    assert out.chosen in T.SIMPLICITY_ORDER
    for name in ("model_card.md", "models.joblib", "fold_scores.csv", "odds_ratios.csv",
                 "result.json"):  # fmt: skip
        assert (tmp_path / "out" / name).exists()
    assert out.dataset.sha256[:10] in out.dataset.snapshot
    assert "association" in (tmp_path / "out" / "model_card.md").read_text(encoding="utf-8")


def test_mlflow_logging(workbook, tmp_path):
    out = T.run_training(
        TrainInput(
            workbook=workbook,
            n_splits=4,
            n_repeats_importance=1,
            track=False,
            out_dir=tmp_path / "out",
            raw_dir=tmp_path / "raw",
            snapshot_dir=tmp_path / "snap",
        )  # fmt: skip
    )
    from src.modelling.tracking import log_run

    inp = TrainInput(workbook=workbook, n_splits=4)
    run_id = log_run(out, inp, tmp_path / "out", root=tmp_path / "mlruns")
    import mlflow

    run = mlflow.get_run(run_id)
    assert run.data.tags["data_sha256"] == out.dataset.sha256
    assert "m1_logistic.pr_auc_mean" in run.data.metrics


def clean_csv_frame() -> pd.DataFrame:
    """Same synthetic answers in the clean data-v1.0 layout (base_id, use_strict)."""
    df = synthetic_sheet()
    df["base_id"] = df["prompt_id"].str[:3]
    df["use_strict"] = [i % 7 != 0 for i in range(len(df))]
    df["sephora_named"] = df.pop("sephora_word_in_answer")
    return df


def test_reads_clean_csv_and_uses_base_id(tmp_path):
    path = tmp_path / "responses_clean_v1.0.csv"
    clean_csv_frame().to_csv(path, index=False)
    raw = read_final_data(path)
    table, _, agreement = build_features(raw, BRANDS, "Sephora India", FACTORS)
    assert set(table["group_id"]) == set(raw["base_id"])
    assert agreement == 1.0


def test_strict_drops_use_strict_false_rows():
    df = clean_csv_frame()
    full, _, _ = build_features(df, BRANDS, "Sephora India", FACTORS)
    strict, excluded, _ = build_features(df, BRANDS, "Sephora India", FACTORS, strict=True)
    assert excluded["use_strict = false"] == len(full) - len(strict) > 0


def test_strict_requires_column():
    with pytest.raises(ValueError, match="use_strict"):
        build_features(synthetic_sheet(), BRANDS, "Sephora India", FACTORS, strict=True)
