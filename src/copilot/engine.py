"""Content copilot entry points.

ingest_knowledge()  approved docs -> chunks -> embeddings -> kb_chunks (pgvector)
draft_content()     opportunity -> retrieve approved chunks -> grounded LLM draft ->
                    rule-based grounding check -> content_variants (status 'draft')
Every draft waits for human review; nothing is published automatically.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.config import Settings
from src.copilot.drafting import GenerateFn, check_grounding, generate_draft, retrieval_query
from src.copilot.knowledge import KNOWLEDGE_DIR, EmbedFn, doc_chunks, embed_texts, load_docs
from src.copilot.models import DraftInput, DraftOutput, IngestOutput
from src.copilot.repository import CopilotRepository

logger = logging.getLogger(__name__)


def ingest_knowledge(
    settings: Settings,
    repo: CopilotRepository,
    directory: Path = KNOWLEDGE_DIR,
    embed_fn: EmbedFn | None = None,
) -> IngestOutput:
    docs = load_docs(directory)
    if not docs:
        raise ValueError(f"No approved documents in {directory}. See its README.md.")
    api_key = settings.require("openai_api_key")
    cfg = settings.project.analysis
    embed = embed_fn or embed_texts
    skipped = n_chunks = 0
    for doc in docs:
        if repo.doc_sha(doc.doc_id) == doc.content_sha:
            skipped += 1
            continue
        chunks = doc_chunks(doc)
        vectors = embed(cfg, api_key, [c.text for c in chunks])
        n_chunks += repo.save_doc(doc, chunks, vectors, cfg.embedding_model)
        logger.info("Ingested %s (%d chunks)", doc.doc_id, len(chunks))
    return IngestOutput(n_docs=len(docs), n_skipped_unchanged=skipped, n_chunks=n_chunks)


def draft_content(
    inp: DraftInput,
    settings: Settings,
    repo: CopilotRepository,
    embed_fn: EmbedFn | None = None,
    generate_fn: GenerateFn | None = None,
) -> DraftOutput:
    api_key = settings.require("openai_api_key")
    cfg = settings.project.analysis
    ctx = repo.load_context(inp.opportunity_id)
    if inp.require_approved_recommendation and ctx.recommendation_status != "approved":
        raise ValueError("The recommendation for this opportunity has not been approved yet.")

    query_vec = (embed_fn or embed_texts)(cfg, api_key, [retrieval_query(ctx)])[0]
    chunks = repo.search(query_vec, inp.k)
    if not chunks:
        raise ValueError("Knowledge base is empty. Add approved docs and run ingestion first.")

    draft = (generate_fn or generate_draft)(cfg, api_key, ctx, chunks)
    grounding = check_grounding(draft, chunks)
    variant_id, version = repo.save_variant(ctx, draft, grounding, generated_by=cfg.model)
    logger.info("Draft v%d for %s grounded=%s", version, ctx.opportunity_id, grounding.grounded)
    return DraftOutput(
        variant_id=variant_id,
        opportunity_id=ctx.opportunity_id,
        version=version,
        title=draft.title,
        content_type=draft.content_type,
        grounded=grounding.grounded,
        grounding=grounding,
    )
