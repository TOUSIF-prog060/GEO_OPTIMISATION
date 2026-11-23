"""Database access for the opportunity engine."""

from __future__ import annotations

from typing import Any, Protocol

import psycopg

from src.diagnostics.repository import PostgresDiagnosticsRepository
from src.opportunities.models import (
    GoldVisibility,
    Opportunity,
    OpportunityInputs,
    Recommendation,
)


class OpportunityRepository(Protocol):
    def load_inputs(self, run_id: str) -> OpportunityInputs: ...
    def save_opportunity(self, opp: Opportunity) -> str: ...
    def save_recommendation(self, rec: Recommendation) -> str: ...


class PostgresOpportunityRepository:
    def __init__(self, conn: psycopg.Connection, parser_version: str = "v1") -> None:
        self.conn = conn
        self.diag = PostgresDiagnosticsRepository(conn)
        self.parser_version = parser_version

    def load_inputs(self, run_id: str) -> OpportunityInputs:
        vis = self.conn.execute(
            """
            SELECT brand_id, category, n_responses, mention_rate::float, avg_rank::float,
                   citation_share::float, positive_rate::float
            FROM gold_visibility WHERE run_id = %s AND metric_version = 'v1'
            """,
            (run_id,),
        ).fetchall()
        keys = ["brand_id", "category", "n_responses", "mention_rate", "avg_rank",
                "citation_share", "positive_rate"]  # fmt: skip
        brands = self.diag.load_brands()
        target = next((b for b in brands if b.is_target), None)
        agree = None
        if target:
            row = self.conn.execute(
                "SELECT agreement_rate::float FROM gold_repeatability "
                "WHERE run_id = %s AND brand_id = %s AND metric_version = 'v1'",
                (run_id, target.brand_id),
            ).fetchone()
            agree = row[0] if row else None
        return OpportunityInputs(
            run_id=run_id,
            brands=brands,
            responses=self.diag.load_responses(run_id),
            visibility=[GoldVisibility(**dict(zip(keys, r, strict=True))) for r in vis],
            mentions=self.diag.load_mentions(run_id, self.parser_version),
            citations=self.diag.load_citations(run_id, self.parser_version),
            domains=self.diag.load_domains(),
            accuracy_checks=self.diag.load_accuracy_checks(run_id, "v1"),
            facts=self.diag.load_facts(),
            repeat_agreement=agree,
        )

    def save_opportunity(self, opp: Opportunity) -> str:
        """Upsert on (run_id, dedupe_key, rule_version). Keeps an existing status."""
        row = self.conn.execute(
            """
            INSERT INTO opportunities
              (run_id, brand_id, prompt_id, category, gap_type, severity, evidence_response_ids,
               details, title, rationale, validation_approach, confidence, effort,
               priority_score, metric_name, target_value, benchmark_value, benchmark_brand_id,
               dedupe_key, rule_version)
            VALUES (%(run_id)s, %(brand_id)s, %(prompt_id)s, %(category)s, %(gap_type)s,
                    %(severity)s, %(evidence_response_ids)s::uuid[], '{}', %(title)s,
                    %(rationale)s, %(validation_approach)s, %(confidence)s, %(effort)s,
                    %(priority_score)s, %(metric_name)s, %(target_value)s, %(benchmark_value)s,
                    %(benchmark_brand_id)s, %(dedupe_key)s, %(rule_version)s)
            ON CONFLICT (run_id, dedupe_key, rule_version) DO UPDATE
            SET severity = EXCLUDED.severity,
                evidence_response_ids = EXCLUDED.evidence_response_ids,
                title = EXCLUDED.title, rationale = EXCLUDED.rationale,
                validation_approach = EXCLUDED.validation_approach,
                confidence = EXCLUDED.confidence, effort = EXCLUDED.effort,
                priority_score = EXCLUDED.priority_score, target_value = EXCLUDED.target_value,
                benchmark_value = EXCLUDED.benchmark_value,
                benchmark_brand_id = EXCLUDED.benchmark_brand_id
            RETURNING opportunity_id
            """,
            opp.model_dump(),
        ).fetchone()
        self.conn.commit()
        return str(row[0])

    def save_recommendation(self, rec: Recommendation) -> str:
        """Upsert on (opportunity_id, generated_by). Keeps an existing review decision."""
        row = self.conn.execute(
            """
            INSERT INTO recommendations
              (opportunity_id, action, rationale, priority, generated_by, evidence_response_ids)
            VALUES (%(opportunity_id)s, %(action)s, %(rationale)s, %(priority)s,
                    %(generated_by)s, %(evidence_response_ids)s::uuid[])
            ON CONFLICT (opportunity_id, generated_by) DO UPDATE
            SET action = EXCLUDED.action, rationale = EXCLUDED.rationale,
                priority = EXCLUDED.priority,
                evidence_response_ids = EXCLUDED.evidence_response_ids
            RETURNING recommendation_id
            """,
            rec.model_dump(),
        ).fetchone()
        self.conn.commit()
        return str(row[0])


def _rows(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def list_opportunities(conn: psycopg.Connection, run_id: str | None = None) -> list[dict]:
    return _rows(
        conn.execute(
            """
            SELECT o.opportunity_id::text, o.run_id::text, o.gap_type, o.category, o.title,
                   o.rationale, o.validation_approach, o.severity::float, o.confidence::float,
                   o.effort, o.priority_score::float, o.status, o.metric_name,
                   o.target_value::float, o.benchmark_value::float,
                   cardinality(o.evidence_response_ids) AS n_evidence,
                   r.recommendation_id::text, r.action, r.status AS rec_status,
                   r.reviewed_by, r.review_notes, o.created_at
            FROM opportunities o
            LEFT JOIN recommendations r ON r.opportunity_id = o.opportunity_id
            WHERE %(run_id)s::uuid IS NULL OR o.run_id = %(run_id)s::uuid
            ORDER BY o.priority_score DESC NULLS LAST
            """,
            {"run_id": run_id},
        )
    )


def load_evidence(conn: psycopg.Connection, opportunity_id: str, limit: int = 20) -> list[dict]:
    return _rows(
        conn.execute(
            """
            SELECT b.response_id::text, b.provider, p.text AS prompt,
                   left(b.answer_text, 600) AS answer
            FROM opportunities o
            JOIN LATERAL unnest(o.evidence_response_ids) AS e(response_id) ON true
            JOIN bronze_responses b ON b.response_id = e.response_id
            JOIN prompts p ON p.prompt_id = b.prompt_id
            WHERE o.opportunity_id = %s LIMIT %s
            """,
            (opportunity_id, limit),
        )
    )


def review_recommendation(
    conn: psycopg.Connection, recommendation_id: str, status: str, reviewer: str, notes: str = ""
) -> None:
    if status not in {"approved", "rejected", "proposed"}:
        raise ValueError(f"bad status {status}")
    conn.execute(
        """
        UPDATE recommendations SET status = %s, reviewed_by = %s, review_notes = %s,
               reviewed_at = now() WHERE recommendation_id = %s
        """,
        (status, reviewer, notes or None, recommendation_id),
    )
    conn.execute(
        """
        UPDATE opportunities
        SET status = CASE WHEN %s = 'approved' THEN 'in_progress' ELSE status END
        WHERE opportunity_id = (
            SELECT opportunity_id FROM recommendations WHERE recommendation_id = %s
        )
        """,
        (status, recommendation_id),
    )
    conn.commit()
