"""Typed inputs and outputs for the content copilot."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

ContentType = Literal["faq", "buying_guide", "product_description", "content_brief"]


class KnowledgeDoc(BaseModel):
    doc_id: str
    title: str
    source_url: str
    verified_at: date
    text: str
    content_sha: str


class Chunk(BaseModel):
    chunk_id: int | None = None
    doc_id: str
    chunk_no: int
    text: str
    title: str | None = None
    source_url: str | None = None
    score: float | None = None  # cosine similarity when retrieved


class OpportunityContext(BaseModel):
    opportunity_id: str
    title: str
    rationale: str
    category: str | None
    gap_type: str
    action: str | None  # recommendation text
    recommendation_id: str | None
    recommendation_status: str | None
    brand_name: str
    evidence: list[dict[str, str]]  # prompt / answer excerpts
    evidence_response_ids: list[str]


class GeneratedDraft(BaseModel):
    """Structured LLM output."""

    title: str
    content_type: ContentType
    body: str
    cited_chunk_ids: list[int]
    unsupported_claims: list[str]
    needs_more_info: bool


class Grounding(BaseModel):
    retrieved_chunk_ids: list[int]
    cited_chunk_ids: list[int]
    invalid_citations: list[int]  # cited but not retrieved
    unsupported_claims: list[str]
    needs_more_info: bool

    @property
    def grounded(self) -> bool:
        return (
            bool(self.cited_chunk_ids)
            and not self.invalid_citations
            and not self.unsupported_claims
            and not self.needs_more_info
        )


class DraftInput(BaseModel):
    opportunity_id: str
    k: int = Field(default=6, ge=1, le=20)
    require_approved_recommendation: bool = False


class DraftOutput(BaseModel):
    variant_id: str
    opportunity_id: str
    version: int
    title: str
    content_type: str
    grounded: bool
    grounding: Grounding


class IngestOutput(BaseModel):
    n_docs: int
    n_skipped_unchanged: int
    n_chunks: int
