"""Grounded drafting: LLM writes from retrieved, approved chunks only; rules check grounding."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from src.config import AnalysisConfig
from src.copilot.models import Chunk, GeneratedDraft, Grounding, OpportunityContext
from src.discovery.providers import parse_openai

GenerateFn = Callable[[AnalysisConfig, str, OpportunityContext, list[Chunk]], GeneratedDraft]

INSTRUCTIONS = (
    "You are a content copilot for a brand's marketing team. Draft web content that helps AI "
    "answer engines describe the brand accurately for the shopper questions given.\n"
    "Hard rules:\n"
    "1. Use ONLY facts found in the numbered SOURCES. Never add prices, offers, policies, "
    "product claims or statistics that are not in the sources.\n"
    "2. Put the chunk id in square brackets after each factual sentence, e.g. [12].\n"
    "3. List any claim you wanted to make but could not support in unsupported_claims, "
    "and set needs_more_info=true if the sources are not enough for useful content.\n"
    "4. No superlatives you cannot source (e.g. 'best', 'cheapest'), no fake reviews, "
    "no statements about competitors beyond what the sources say.\n"
    "5. Write in clear English for Indian shoppers, using Markdown headings and short FAQs."
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content_type": {
            "type": "string",
            "enum": ["faq", "buying_guide", "product_description", "content_brief"],
        },
        "body": {"type": "string"},
        "cited_chunk_ids": {"type": "array", "items": {"type": "integer"}},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "needs_more_info": {"type": "boolean"},
    },
    "required": ["title", "content_type", "body", "cited_chunk_ids", "unsupported_claims",
                 "needs_more_info"],
    "additionalProperties": False,
}  # fmt: skip


def retrieval_query(ctx: OpportunityContext) -> str:
    parts = [ctx.title, ctx.rationale, ctx.action or "", ctx.category or ""]
    parts += [e.get("prompt", "") for e in ctx.evidence[:5]]
    return "\n".join(p for p in parts if p)


def build_request(cfg: AnalysisConfig, ctx: OpportunityContext, chunks: list[Chunk]) -> dict:
    sources = "\n\n".join(f"[{c.chunk_id}] ({c.title} — {c.source_url})\n{c.text}" for c in chunks)
    questions = "\n".join(f"- {e.get('prompt', '')}" for e in ctx.evidence[:8])
    user = (
        f"Brand: {ctx.brand_name}\n"
        f"Opportunity: {ctx.title}\nWhy: {ctx.rationale}\n"
        f"Recommended action: {ctx.action or 'n/a'}\n\n"
        f"Shopper questions where the gap was observed:\n{questions or '- n/a'}\n\n"
        f"SOURCES:\n{sources or '(none)'}"
    )
    return {
        "model": cfg.model,
        "instructions": INSTRUCTIONS,
        "input": user,
        "text": {"format": {"type": "json_schema", "name": "draft", "schema": SCHEMA,
                            "strict": True}},
    }  # fmt: skip


def generate_draft(
    cfg: AnalysisConfig,
    api_key: str,
    ctx: OpportunityContext,
    chunks: list[Chunk],
    client: Any | None = None,
) -> GeneratedDraft:
    from openai import OpenAI  # lazy

    sdk = client or OpenAI(api_key=api_key, timeout=cfg.timeout_s)
    resp = sdk.responses.create(**build_request(cfg, ctx, chunks))
    text = parse_openai(resp.model_dump(mode="json"))[0]
    if not text:
        raise ValueError("empty draft response")
    return GeneratedDraft.model_validate(json.loads(text))


def check_grounding(draft: GeneratedDraft, retrieved: list[Chunk]) -> Grounding:
    ids = [c.chunk_id for c in retrieved if c.chunk_id is not None]
    cited = sorted(set(draft.cited_chunk_ids))
    return Grounding(
        retrieved_chunk_ids=ids,
        cited_chunk_ids=cited,
        invalid_citations=[c for c in cited if c not in set(ids)],
        unsupported_claims=draft.unsupported_claims,
        needs_more_info=draft.needs_more_info,
    )
