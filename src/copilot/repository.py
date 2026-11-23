"""Database access for the content copilot (knowledge base + content variants)."""

from __future__ import annotations

from typing import Any, Protocol

import psycopg
from psycopg.types.json import Jsonb

from src.copilot.knowledge import to_vector_literal
from src.copilot.models import Chunk, GeneratedDraft, Grounding, KnowledgeDoc, OpportunityContext


class CopilotRepository(Protocol):
    def doc_sha(self, doc_id: str) -> str | None: ...
    def save_doc(self, doc: KnowledgeDoc, chunks: list[Chunk], vectors: list[list[float]],
                 embed_model: str) -> int: ...  # fmt: skip
    def search(self, vector: list[float], k: int) -> list[Chunk]: ...
    def load_context(self, opportunity_id: str) -> OpportunityContext: ...
    def save_variant(self, ctx: OpportunityContext, draft: GeneratedDraft, grounding: Grounding,
                     generated_by: str) -> tuple[str, int]: ...  # fmt: skip


class PostgresCopilotRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def doc_sha(self, doc_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT content_sha FROM kb_documents WHERE doc_id = %s", (doc_id,)
        ).fetchone()
        return row[0] if row else None

    def save_doc(
        self, doc: KnowledgeDoc, chunks: list[Chunk], vectors: list[list[float]], embed_model: str
    ) -> int:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kb_documents (doc_id, title, source_url, verified_at, content_sha)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (doc_id) DO UPDATE
                SET title = EXCLUDED.title, source_url = EXCLUDED.source_url,
                    verified_at = EXCLUDED.verified_at, content_sha = EXCLUDED.content_sha,
                    updated_at = now()
                """,
                (doc.doc_id, doc.title, doc.source_url, doc.verified_at, doc.content_sha),
            )
            cur.execute("DELETE FROM kb_chunks WHERE doc_id = %s", (doc.doc_id,))
            cur.executemany(
                """
                INSERT INTO kb_chunks (doc_id, chunk_no, text, embedding, embed_model)
                VALUES (%s, %s, %s, %s::vector, %s)
                """,
                [
                    (c.doc_id, c.chunk_no, c.text, to_vector_literal(v), embed_model)
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )
        self.conn.commit()
        return len(chunks)

    def search(self, vector: list[float], k: int) -> list[Chunk]:
        cur = self.conn.execute(
            """
            SELECT c.chunk_id, c.doc_id, c.chunk_no, c.text, d.title, d.source_url,
                   1 - (c.embedding <=> %s::vector) AS score
            FROM kb_chunks c JOIN kb_documents d USING (doc_id)
            ORDER BY c.embedding <=> %s::vector LIMIT %s
            """,
            (to_vector_literal(vector), to_vector_literal(vector), k),
        )
        cols = [d.name for d in cur.description]
        return [Chunk(**dict(zip(cols, r, strict=True))) for r in cur.fetchall()]

    def load_context(self, opportunity_id: str) -> OpportunityContext:
        row = self.conn.execute(
            """
            SELECT o.opportunity_id::text, o.title, o.rationale, o.category, o.gap_type,
                   r.action, r.recommendation_id::text, r.status, b.name,
                   o.evidence_response_ids::text[]
            FROM opportunities o
            JOIN brands b ON b.brand_id = o.brand_id
            LEFT JOIN recommendations r ON r.opportunity_id = o.opportunity_id
            WHERE o.opportunity_id = %s
            """,
            (opportunity_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Opportunity {opportunity_id} not found")
        ev = self.conn.execute(
            """
            SELECT p.text, left(b.answer_text, 500)
            FROM bronze_responses b JOIN prompts p USING (prompt_id)
            WHERE b.response_id = ANY(%s::uuid[]) LIMIT 8
            """,
            (row[9],),
        ).fetchall()
        return OpportunityContext(
            opportunity_id=row[0], title=row[1] or "", rationale=row[2] or "", category=row[3],
            gap_type=row[4], action=row[5], recommendation_id=row[6],
            recommendation_status=row[7], brand_name=row[8],
            evidence=[{"prompt": p, "answer": a or ""} for p, a in ev],
            evidence_response_ids=list(row[9] or []),
        )  # fmt: skip

    def save_variant(
        self,
        ctx: OpportunityContext,
        draft: GeneratedDraft,
        grounding: Grounding,
        generated_by: str,
    ) -> tuple[str, int]:
        with self.conn.transaction():
            version = self.conn.execute(
                "SELECT coalesce(max(version), 0) + 1 FROM content_variants "
                "WHERE opportunity_id = %s",
                (ctx.opportunity_id,),
            ).fetchone()[0]
            row = self.conn.execute(
                """
                INSERT INTO content_variants
                  (opportunity_id, recommendation_id, version, title, body, generated_by, status,
                   content_type, source_chunk_ids, retrieved_chunk_ids, evidence_response_ids,
                   grounding)
                VALUES (%s, %s, %s, %s, %s, %s, 'draft', %s, %s, %s, %s::uuid[], %s)
                RETURNING variant_id
                """,
                (
                    ctx.opportunity_id,
                    ctx.recommendation_id,
                    version,
                    draft.title,
                    draft.body,
                    generated_by,
                    draft.content_type,
                    grounding.cited_chunk_ids,
                    grounding.retrieved_chunk_ids,
                    ctx.evidence_response_ids,
                    Jsonb(grounding.model_dump() | {"grounded": grounding.grounded}),
                ),  # fmt: skip
            ).fetchone()
        self.conn.commit()
        return str(row[0]), version


def _rows(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def list_variants(conn: psycopg.Connection, opportunity_id: str | None = None) -> list[dict]:
    return _rows(
        conn.execute(
            """
            SELECT v.variant_id::text, v.opportunity_id::text, o.title AS opportunity, v.version,
                   v.title, v.content_type, v.body, v.status, v.generated_by,
                   (v.grounding->>'grounded')::boolean AS grounded, v.grounding,
                   v.reviewed_by, v.review_notes, v.created_at
            FROM content_variants v JOIN opportunities o USING (opportunity_id)
            WHERE %(o)s::uuid IS NULL OR v.opportunity_id = %(o)s::uuid
            ORDER BY v.created_at DESC
            """,
            {"o": opportunity_id},
        )
    )


def load_chunks(conn: psycopg.Connection, chunk_ids: list[int]) -> list[dict]:
    return _rows(
        conn.execute(
            """
            SELECT c.chunk_id, d.title, d.source_url, c.text
            FROM kb_chunks c JOIN kb_documents d USING (doc_id) WHERE c.chunk_id = ANY(%s)
            ORDER BY c.chunk_id
            """,
            (chunk_ids,),
        )
    )


def kb_stats(conn: psycopg.Connection) -> dict[str, int]:
    row = conn.execute(
        "SELECT (SELECT count(*) FROM kb_documents), (SELECT count(*) FROM kb_chunks)"
    ).fetchone()
    return {"documents": row[0], "chunks": row[1]}


def review_variant(
    conn: psycopg.Connection, variant_id: str, status: str, reviewer: str, notes: str = ""
) -> None:
    if status not in {"approved", "rejected", "draft"}:
        raise ValueError(f"bad status {status}")
    conn.execute(
        """
        UPDATE content_variants SET status = %s, reviewed_by = %s, review_notes = %s,
               reviewed_at = now() WHERE variant_id = %s
        """,
        (status, reviewer, notes or None, variant_id),
    )
    conn.commit()
