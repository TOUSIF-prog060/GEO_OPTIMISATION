"""Typed inputs and outputs for the opportunity engine."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.diagnostics.models import (
    AccuracyCheckRow,
    BrandRef,
    CitationRow,
    DomainRef,
    FactRef,
    MentionRow,
    ResponseRecord,
)

GapType = Literal[
    "visibility_gap",
    "ranking_gap",
    "citation_gap",
    "sentiment_gap",
    "accuracy_issue",
    "unstable_visibility",
]
Effort = Literal["low", "medium", "high"]


class OpportunityRules(BaseModel):
    """Thresholds for rules v1. Defaults are documented in DECISION_LOG."""

    rule_version: str = "v1"
    min_responses: int = Field(default=3, ge=1)  # ignore categories with fewer answers
    mention_gap: float = 0.15  # competitor mention rate - target mention rate
    rank_gap: float = 1.0  # target avg rank - competitor avg rank
    citation_gap: float = 0.10
    positive_gap: float = 0.20
    repeat_agreement: float = 0.70  # below this, target visibility is "unstable"
    max_evidence: int = 50
    effort: dict[str, Effort] = {
        "visibility_gap": "medium",
        "ranking_gap": "medium",
        "citation_gap": "high",
        "sentiment_gap": "medium",
        "accuracy_issue": "low",
        "unstable_visibility": "high",
    }


class GoldVisibility(BaseModel):
    brand_id: int
    category: str
    n_responses: int
    mention_rate: float | None = None
    avg_rank: float | None = None
    citation_share: float | None = None
    positive_rate: float | None = None


class OpportunityInputs(BaseModel):
    """Everything the rules need for one run, loaded once."""

    run_id: str
    brands: list[BrandRef]
    responses: list[ResponseRecord]
    visibility: list[GoldVisibility]
    mentions: list[MentionRow]
    citations: list[CitationRow]
    domains: dict[str, DomainRef]
    accuracy_checks: list[AccuracyCheckRow] = Field(default_factory=list)
    facts: dict[str, FactRef] = Field(default_factory=dict)
    repeat_agreement: float | None = None  # target brand, from gold_repeatability

    @property
    def target(self) -> BrandRef:
        return next(b for b in self.brands if b.is_target)


class Opportunity(BaseModel):
    run_id: str
    brand_id: int  # the target brand
    gap_type: GapType
    category: str | None
    prompt_id: str | None = None
    title: str
    rationale: str
    validation_approach: str
    metric_name: str | None = None
    target_value: float | None = None
    benchmark_value: float | None = None
    benchmark_brand_id: int | None = None
    severity: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    effort: Effort
    priority_score: float
    evidence_response_ids: list[str]
    dedupe_key: str
    rule_version: str
    opportunity_id: str | None = None  # set once saved


class Recommendation(BaseModel):
    opportunity_id: str
    action: str
    rationale: str
    priority: int
    generated_by: str
    evidence_response_ids: list[str]


class OpportunityInput(BaseModel):
    run_id: str
    rules: OpportunityRules = OpportunityRules()


class OpportunityOutput(BaseModel):
    run_id: str
    n_opportunities: int
    n_recommendations: int
    by_type: dict[str, int]
    opportunity_ids: list[str]
