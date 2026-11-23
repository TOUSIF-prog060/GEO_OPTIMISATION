"""Typed inputs and outputs for the experimentation lab."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Design = Literal["content_variant", "repeat_baseline"]


class CreateExperimentInput(BaseModel):
    baseline_run_id: str
    design: Design = "content_variant"
    variant_id: str | None = None
    opportunity_id: str | None = None
    prompt_ids: list[str] | None = None  # None -> evidence prompts of the opportunity, else all
    hypothesis: str | None = None
    created_by: str = "user"


class BaselineRun(BaseModel):
    run_id: str
    panel_version: str
    provider: str


class Counts(BaseModel):
    x: int  # responses mentioning the brand
    n: int  # successful responses


class ResultRow(BaseModel):
    experiment_id: str
    brand_id: int
    metric: str = "mention_rate"
    baseline_value: float | None
    retest_value: float | None
    delta: float | None
    ci_low: float | None
    ci_high: float | None
    p_value: float | None
    n_baseline: int
    n_retest: int
    interpretation: str


class RetestInput(BaseModel):
    experiment_id: str
    repeats: int = Field(default=3, ge=1, le=10)


class ExperimentOutput(BaseModel):
    experiment_id: str
    status: str
    retest_run_id: str | None = None
    results: list[ResultRow] = Field(default_factory=list)
