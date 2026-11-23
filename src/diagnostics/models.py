"""Typed inputs and outputs for the diagnostics engine."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Sentiment = Literal["positive", "neutral", "negative", "mixed"]
DomainType = Literal["brand_owned", "competitor", "retailer", "editorial", "ugc", "video", "other"]


class BrandRef(BaseModel):
    brand_id: int
    name: str
    aliases: list[str]
    is_target: bool = False


class DomainRef(BaseModel):
    domain: str
    domain_type: DomainType
    brand_id: int | None = None


class ResponseRecord(BaseModel):
    """One stored Bronze response, joined with its prompt."""

    response_id: str
    run_id: str
    prompt_id: str
    provider: str
    category: str
    repeat_no: int = 1
    prompt_text: str = ""
    answer_text: str | None = None
    raw_response: dict[str, Any] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.raw_response is not None


class CitationRow(BaseModel):
    response_id: str
    run_id: str
    position: int = Field(ge=1)
    url: str
    domain: str
    title: str | None = None
    parser_version: str


class MentionRow(BaseModel):
    response_id: str
    run_id: str
    brand_id: int
    mentioned: bool
    mention_count: int = 0
    first_char_pos: int | None = None
    rank_in_list: int | None = None
    is_recommended: bool | None = None
    sentiment: Sentiment | None = None
    snippet: str | None = None
    extraction_method: str = "alias_rule"
    confidence: float | None = None  # None for deterministic rules
    parser_version: str


class ProductRef(BaseModel):
    product_id: str
    product_name: str
    maker: str | None = None
    aliases: list[str] = Field(default_factory=list)
    category: str


class ProductMentionRow(BaseModel):
    response_id: str
    run_id: str
    product_id: str
    mention_count: int
    first_char_pos: int | None = None
    rank_in_list: int | None = None
    snippet: str | None = None
    extraction_method: str = "alias_rule"
    confidence: float | None = None
    parser_version: str


ValueType = Literal["text", "number", "boolean"]
Verdict = Literal["match", "mismatch", "not_mentioned", "unverifiable"]


class FactRef(BaseModel):
    fact_id: str
    subject_type: Literal["brand", "product"]
    subject: str  # brand name or product_id
    attribute: str
    approved_value: str
    value_type: ValueType
    tolerance: float | None = None


class AccuracyCheckRow(BaseModel):
    response_id: str
    run_id: str
    fact_id: str
    stated_value: str | None
    approved_value: str
    verdict: Verdict
    extraction_method: str = "llm_extract"
    extracted_by: str | None = None
    checker_version: str


class AccuracyRow(BaseModel):
    run_id: str
    subject: str
    attribute: str
    n_checked: int
    n_match: int
    n_mismatch: int
    n_not_mentioned: int
    n_unverifiable: int
    accuracy_rate: float | None
    metric_version: str


class RepeatabilityRow(BaseModel):
    run_id: str
    brand_id: int
    n_prompts: int
    agreement_rate: float | None
    mean_within_prompt_sd: float | None
    metric_version: str


class VisibilityRow(BaseModel):
    run_id: str
    brand_id: int
    category: str  # 'ALL' = whole run
    n_responses: int
    mention_rate: float | None
    share_of_voice: float | None
    avg_rank: float | None
    citation_share: float | None
    positive_rate: float | None
    metric_version: str


class SourceShareRow(BaseModel):
    run_id: str
    category: str
    domain: str
    domain_type: str
    n_citations: int
    citation_share: float
    metric_version: str


class DiagnoseInput(BaseModel):
    run_id: str
    parser_version: str = "v1"
    metric_version: str = "v1"


class DiagnoseOutput(BaseModel):
    run_id: str
    n_responses: int
    n_skipped_errors: int
    n_citations: int
    n_mentions: int
    n_visibility_rows: int
    n_source_rows: int
    n_product_mentions: int = 0
    n_repeatability_rows: int = 0


class MentionToLabel(BaseModel):
    mention_id: int
    brand_name: str
    prompt_text: str
    answer_text: str


class MentionLabel(BaseModel):
    sentiment: Sentiment
    is_recommended: bool


class ClassifyInput(BaseModel):
    run_id: str
    parser_version: str = "v1"
    max_workers: int = Field(default=4, ge=1, le=16)


class ClassifyOutput(BaseModel):
    run_id: str
    n_classified: int
    n_failed: int
    model: str


class AccuracyInput(BaseModel):
    run_id: str
    checker_version: str = "v1"
    metric_version: str = "v1"
    max_workers: int = Field(default=4, ge=1, le=16)


class AccuracyOutput(BaseModel):
    run_id: str
    n_responses_checked: int
    n_checks: int
    n_failed: int
    model: str
