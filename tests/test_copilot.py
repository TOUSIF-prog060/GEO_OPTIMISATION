import json
import math
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import AnalysisConfig, Settings, load_project_config
from src.copilot import DraftInput, draft_content, ingest_knowledge
from src.copilot.drafting import build_request, check_grounding, generate_draft
from src.copilot.knowledge import chunk_text, embed_texts, load_docs, parse_doc, to_vector_literal
from src.copilot.models import Chunk, GeneratedDraft, OpportunityContext

DOC = """---
title: Sephora India Delivery FAQ
source_url: https://www.sephora.in/faq
verified_at: 2026-11-23
---
Orders are delivered in 3-5 working days.

Cash on delivery is available on eligible orders.
"""


def write_doc(tmp_path: Path, name: str = "delivery.md", body: str = DOC) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def settings(key: str | None = "k") -> Settings:
    return Settings(project=load_project_config(), openai_api_key=key)


def fake_embed(cfg, key, texts):
    """Deterministic 3-d 'embedding': counts of a few keywords."""
    return [[t.lower().count(w) + 0.01 for w in ("deliver", "cash", "sunscreen")] for t in texts]


# ---------------------------------------------------------------- knowledge


def test_parse_doc_and_readme_ignored(tmp_path: Path) -> None:
    write_doc(tmp_path)
    (tmp_path / "README.md").write_text("ignore me", encoding="utf-8")
    (doc,) = load_docs(tmp_path)
    assert doc.doc_id == "delivery" and doc.verified_at == date(2026, 11, 23)
    assert doc.text.startswith("Orders") and len(doc.content_sha) == 64


@pytest.mark.parametrize(
    "body",
    [
        "no front matter",
        "---\ntitle: x\n---\ntext",
        "---\ntitle: x\nsource_url: u\nverified_at: 2026-01-01\n---\n",
    ],
)
def test_parse_doc_rejects_incomplete(tmp_path: Path, body: str) -> None:
    with pytest.raises(ValueError):
        parse_doc(write_doc(tmp_path, body=body))


def test_chunk_text_sizes_and_overlap() -> None:
    paras = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(10))
    chunks = chunk_text(paras, size=500, overlap=50)
    assert len(chunks) > 1 and all(len(c) <= 500 for c in chunks)
    long = "x " * 2000
    parts = chunk_text(long, size=300, overlap=50)
    assert all(len(p) <= 300 for p in parts) and len(parts) > 10


def test_vector_literal_and_embed_batches() -> None:
    assert to_vector_literal([0.5, 1, -2.25]) == "[0.5,1,-2.25]"
    calls = []

    def create(model, input):
        calls.append(len(input))
        return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0]) for _ in input])

    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    out = embed_texts(AnalysisConfig(), "k", ["t"] * 130, client=client)
    assert len(out) == 130 and calls == [64, 64, 2]


# ---------------------------------------------------------------- fake repo


class FakeRepo:
    def __init__(self) -> None:
        self.docs: dict[str, str] = {}
        self.chunks: list[tuple[Chunk, list[float]]] = []
        self.variants: list = []

    def doc_sha(self, doc_id):
        return self.docs.get(doc_id)

    def save_doc(self, doc, chunks, vectors, embed_model):
        self.docs[doc.doc_id] = doc.content_sha
        self.chunks = [c for c in self.chunks if c[0].doc_id != doc.doc_id]
        for c, v in zip(chunks, vectors, strict=True):
            self.chunks.append((c.model_copy(update={"chunk_id": len(self.chunks) + 1}), v))
        return len(chunks)

    def search(self, vector, k):
        def cos(a, b):
            return sum(x * y for x, y in zip(a, b, strict=True)) / (
                math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
            )

        ranked = sorted(self.chunks, key=lambda cv: cos(vector, cv[1]), reverse=True)
        return [c.model_copy(update={"score": cos(vector, v)}) for c, v in ranked[:k]]

    def load_context(self, opportunity_id):
        return OpportunityContext(
            opportunity_id=opportunity_id, title="Sephora missing from delivery answers",
            rationale="Nykaa mentioned for fast delivery", category="retailer",
            gap_type="visibility_gap", action="Publish a delivery FAQ", recommendation_id="rec1",
            recommendation_status="proposed", brand_name="Sephora India",
            evidence=[{"prompt": "Which site delivers fast?", "answer": "Nykaa"}],
            evidence_response_ids=["r1"],
        )  # fmt: skip

    def save_variant(self, ctx, draft, grounding, generated_by):
        self.variants.append((ctx, draft, grounding, generated_by))
        return f"v{len(self.variants)}", len(self.variants)


def test_ingest_skips_unchanged(tmp_path: Path) -> None:
    write_doc(tmp_path)
    repo = FakeRepo()
    first = ingest_knowledge(settings(), repo, tmp_path, embed_fn=fake_embed)
    assert first.n_chunks >= 1 and first.n_skipped_unchanged == 0
    again = ingest_knowledge(settings(), repo, tmp_path, embed_fn=fake_embed)
    assert again.n_chunks == 0 and again.n_skipped_unchanged == 1


def test_ingest_requires_docs_and_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No approved documents"):
        ingest_knowledge(settings(), FakeRepo(), tmp_path, embed_fn=fake_embed)
    write_doc(tmp_path)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        ingest_knowledge(settings(None), FakeRepo(), tmp_path, embed_fn=fake_embed)


# ---------------------------------------------------------------- drafting


def ingested(tmp_path: Path) -> FakeRepo:
    write_doc(tmp_path, body=DOC.replace("\n\nCash", "\n\n" + "filler " * 150 + "\n\nCash"))
    repo = FakeRepo()
    ingest_knowledge(settings(), repo, tmp_path, embed_fn=fake_embed)
    return repo


def test_draft_grounded(tmp_path: Path) -> None:
    repo = ingested(tmp_path)

    def gen(cfg, key, ctx, chunks):
        assert chunks[0].text.startswith("Orders")  # most relevant chunk first
        return GeneratedDraft(title="Delivery FAQ", content_type="faq",
                              body="Orders arrive in 3-5 days [1].", cited_chunk_ids=[1],
                              unsupported_claims=[], needs_more_info=False)  # fmt: skip

    out = draft_content(DraftInput(opportunity_id="o1", k=2), settings(), repo,
                        embed_fn=fake_embed, generate_fn=gen)  # fmt: skip
    assert out.grounded and out.version == 1 and out.grounding.cited_chunk_ids == [1]
    assert repo.variants[0][3] == settings().project.analysis.model


def test_draft_flags_invented_citation_and_unsupported(tmp_path: Path) -> None:
    repo = ingested(tmp_path)

    def gen(cfg, key, ctx, chunks):
        return GeneratedDraft(title="t", content_type="faq", body="b [99]", cited_chunk_ids=[99],
                              unsupported_claims=["free shipping over 999"],
                              needs_more_info=False)  # fmt: skip

    out = draft_content(DraftInput(opportunity_id="o1"), settings(), repo,
                        embed_fn=fake_embed, generate_fn=gen)  # fmt: skip
    assert not out.grounded
    assert out.grounding.invalid_citations == [99]
    assert out.grounding.unsupported_claims == ["free shipping over 999"]


def test_draft_guards(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Knowledge base is empty"):
        draft_content(DraftInput(opportunity_id="o1"), settings(), FakeRepo(), embed_fn=fake_embed)
    with pytest.raises(ValueError, match="not been approved"):
        draft_content(DraftInput(opportunity_id="o1", require_approved_recommendation=True),
                      settings(), ingested(tmp_path), embed_fn=fake_embed)  # fmt: skip


def test_build_request_and_fake_llm() -> None:
    ctx = FakeRepo().load_context("o1")
    chunks = [Chunk(chunk_id=7, doc_id="d", chunk_no=0, text="COD available", title="FAQ",
                    source_url="https://x")]  # fmt: skip
    req = build_request(AnalysisConfig(model="m"), ctx, chunks)
    assert "[7]" in req["input"] and "Use ONLY facts" in req["instructions"]
    assert req["text"]["format"]["strict"] is True

    payload = {"title": "t", "content_type": "faq", "body": "COD [7]", "cited_chunk_ids": [7],
               "unsupported_claims": [], "needs_more_info": False}  # fmt: skip
    raw = {"output": [{"type": "message", "content": [{"type": "output_text",
           "text": json.dumps(payload)}]}]}  # fmt: skip
    client = SimpleNamespace(responses=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(model_dump=lambda mode=None: raw)))  # fmt: skip
    draft = generate_draft(AnalysisConfig(model="m"), "k", ctx, chunks, client=client)
    assert check_grounding(draft, chunks).grounded
