"""Diagnostics engine: parse Bronze answers into Silver facts and Gold visibility metrics."""

from src.diagnostics.engine import check_accuracy, classify_mentions, diagnose, refresh_gold
from src.diagnostics.models import (
    AccuracyInput,
    AccuracyOutput,
    ClassifyInput,
    ClassifyOutput,
    DiagnoseInput,
    DiagnoseOutput,
)

__all__ = [
    "AccuracyInput",
    "AccuracyOutput",
    "check_accuracy",
    "ClassifyInput",
    "ClassifyOutput",
    "DiagnoseInput",
    "DiagnoseOutput",
    "classify_mentions",
    "diagnose",
    "refresh_gold",
]
