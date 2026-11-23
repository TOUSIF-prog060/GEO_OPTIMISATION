"""Log a training run to MLflow (local, under mlruns/): parameters, per-fold metrics, data
checksum, git commit and artefacts."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from src.config import ROOT_DIR
from src.modelling.models import TrainInput, TrainOutput

log = logging.getLogger(__name__)

EXPERIMENT = "visibility_models"
MLRUNS = ROOT_DIR / "mlruns"


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT_DIR, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        log.warning("Could not read the git commit")
        return "unknown"


def _key(name: str) -> str:
    from src.modelling.train import BASELINE, M1, M2_GB, M2_RF

    return {BASELINE: "baseline", M1: "m1_logistic", M2_RF: "m2_rf", M2_GB: "m2_gb"}[name]


def log_run(o: TrainOutput, inp: TrainInput, out_dir: Path, root: Path = MLRUNS) -> str:
    import mlflow

    root.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri("sqlite:///" + (root / "mlflow.db").as_posix())
    if mlflow.get_experiment_by_name(EXPERIMENT) is None:
        mlflow.create_experiment(EXPERIMENT, artifact_location=(root / "artifacts").as_uri())
    mlflow.set_experiment(EXPERIMENT)
    run_name = f"{o.dataset.target} {o.dataset.analysis_set} {o.dataset.sha256[:8]}"
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags(
            {
                "data_sha256": o.dataset.sha256,
                "data_file": o.dataset.frozen_copy,
                "git_commit": git_commit(),
                "target": o.dataset.target,
                "analysis_set": o.dataset.analysis_set,
                "chosen_model": o.chosen,
            }
        )
        mlflow.log_params(
            {
                "factors": ",".join(o.factors),
                "n_splits": inp.n_splits,
                "seed": inp.seed,
                "cv": "StratifiedGroupKFold by question group",
                "m1": "LogisticRegression C=1.0 (L2)",
                "m2_rf": "RandomForest n=500 min_leaf=5",
                "m2_gb": "HistGradientBoosting depth=3 lr=0.05 iter=200",
                "n_used": o.dataset.n_used,
                "n_positive": o.dataset.n_positive,
            }
        )
        for f in o.folds:
            k = _key(f.model)
            metrics = {f"{k}.f1": f.f1, f"{k}.brier": f.brier}
            if f.pr_auc is not None:
                metrics[f"{k}.pr_auc"] = f.pr_auc
            mlflow.log_metrics(metrics, step=f.fold)
        for s in o.summary:
            k = _key(s.model)
            if s.pr_auc_mean is not None:
                mlflow.log_metric(f"{k}.pr_auc_mean", s.pr_auc_mean)
            mlflow.log_metric(f"{k}.brier_mean", s.brier_mean)
        mlflow.log_artifacts(str(out_dir))
        return run.info.run_id
