"""Read the latest saved training runs for the dashboard (no retraining, no database)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.config import ROOT_DIR

log = logging.getLogger(__name__)

MODELS_DIR = ROOT_DIR / "reports" / "models"
SETS = ("use_in_model", "use_strict")
# Large per-fold detail stays in the files; the dashboard needs summaries.
DROP = ("folds",)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("Could not read model result %s", path)
        return None
    data["run"] = path.parent.name
    data["created"] = path.stat().st_mtime
    for key in DROP:
        data.pop(key, None)
    return data


def latest_runs(models_dir: Path = MODELS_DIR) -> dict[str, dict[str, Any] | None]:
    """Newest result per analysis set: {"use_in_model": {...} | None, "use_strict": ...}."""
    best: dict[str, dict[str, Any] | None] = dict.fromkeys(SETS)
    if not models_dir.exists():
        return best
    for path in models_dir.glob("*/result.json"):
        data = _load(path)
        if not data:
            continue
        kind = data.get("dataset", {}).get("analysis_set", "use_in_model")
        if kind in best and (best[kind] is None or data["created"] > best[kind]["created"]):
            best[kind] = data
    return best


def robustness(main: dict[str, Any] | None, strict: dict[str, Any] | None) -> dict[str, Any]:
    """Does the strict set (no repeated or suspect answers) back the main set's choice?"""
    if not main:
        return {"status": "no_run", "note": "No model has been trained yet."}
    if not strict:
        return {"status": "unchecked", "note": "Train on the strict set to check this result."}
    same_data = main["dataset"]["sha256"] == strict["dataset"]["sha256"]
    if main["chosen"] == strict["chosen"]:
        return {
            "status": "agrees",
            "note": "The strict set picks the same model.",
            "same_data": same_data,
        }
    return {
        "status": "disagrees",
        "note": (
            f"The strict set picks {strict['chosen']} instead. Treat the main set's choice "
            "as tentative."
        ),
        "same_data": same_data,
    }


def model_insights(models_dir: Path = MODELS_DIR) -> dict[str, Any]:
    runs = latest_runs(models_dir)
    main, strict = runs["use_in_model"], runs["use_strict"]
    return {"main": main, "strict": strict, "robustness": robustness(main, strict)}
