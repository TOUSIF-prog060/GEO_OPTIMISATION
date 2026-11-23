"""Input/output models for the visibility models (charter §11: Baseline, M1, M2)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

FACTORS = ["engine", "question_type", "category", "language", "collection_method"]


class TrainInput(BaseModel):
    workbook: Path  # raw collection .xlsx or clean data-v1.0 .csv
    strict: bool = False  # use only use_strict rows (sensitivity check)
    target_brand: str | None = None  # default: the project's target brand
    factors: list[str] = Field(default_factory=lambda: list(FACTORS))
    n_splits: int = Field(default=5, ge=2, le=10)
    n_repeats_importance: int = Field(default=10, ge=1, le=100)
    seed: int = 42
    min_positives_per_factor: int = Field(default=10, ge=1)
    track: bool = True  # log to MLflow
    out_dir: Path | None = None  # default reports/models/<stamp>
    raw_dir: Path | None = None  # default data/raw/collected
    snapshot_dir: Path | None = None  # default data/processed/modelling


class DatasetInfo(BaseModel):
    source_file: str
    frozen_copy: str
    sha256: str
    snapshot: str
    target: str
    analysis_set: str  # "use_in_model" or "use_strict"
    n_rows: int
    n_used: int
    n_positive: int
    excluded: dict[str, int]
    reader_vs_sheet_agreement: float | None  # our alias reader vs the sheet's word search
    n_groups: int


class FoldScore(BaseModel):
    model: str
    fold: int
    n_test: int
    n_pos_test: int
    pr_auc: float | None
    f1: float
    brier: float
    threshold: float


class ModelSummary(BaseModel):
    model: str
    pr_auc_mean: float | None
    pr_auc_sd: float | None
    f1_mean: float
    brier_mean: float
    n_folds: int


class OddsRatio(BaseModel):
    term: str
    odds_ratio: float
    ci_low: float
    ci_high: float
    p_value: float


class Importance(BaseModel):
    factor: str
    pr_auc_drop: float
    sd: float


class CellRate(BaseModel):
    engine: str
    question_type: str
    n: int
    positives: int
    rate: float
    ci_low: float | None
    ci_high: float | None


class TrainOutput(BaseModel):
    dataset: DatasetInfo
    factors: list[str]
    reference_levels: dict[str, str]
    dropped_columns: dict[str, str]  # column -> identical column kept
    n_columns: int
    positives_per_factor: float
    positives_per_column: float
    warnings: list[str]
    folds: list[FoldScore]
    summary: list[ModelSummary]
    chosen: str
    choice_reason: str
    odds_ratios: list[OddsRatio]
    importances: list[Importance]
    baseline_cells: list[CellRate]
    out_dir: str
    mlflow_run_id: str | None = None
