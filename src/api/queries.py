"""Read queries the dashboard needs that no engine module already provides."""

from __future__ import annotations

from typing import Any

import psycopg


def _rows(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def run_detail(conn: psycopg.Connection, run_id: str) -> dict[str, Any] | None:
    rows = _rows(
        conn.execute(
            """
            SELECT r.run_id::text, r.provider, r.model, r.panel_version, r.run_type, r.status,
                   r.started_at, r.finished_at,
                   count(b.response_id) AS n_responses,
                   count(b.response_id) FILTER (WHERE b.error IS NOT NULL) AS n_errors,
                   sum(b.cost_usd)::float AS cost_usd, avg(b.latency_ms)::float AS avg_latency_ms,
                   EXISTS (SELECT 1 FROM gold_visibility g WHERE g.run_id = r.run_id)
                       AS diagnosed
            FROM bronze_runs r LEFT JOIN bronze_responses b USING (run_id)
            WHERE r.run_id = %s GROUP BY r.run_id
            """,
            (run_id,),
        )
    )
    return rows[0] if rows else None


def list_runs_full(conn: psycopg.Connection, limit: int = 50) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            """
            SELECT r.run_id::text, r.provider, r.model, r.panel_version, r.run_type, r.status,
                   r.started_at, r.finished_at,
                   count(b.response_id) AS n_responses,
                   count(b.response_id) FILTER (WHERE b.error IS NOT NULL) AS n_errors,
                   sum(b.cost_usd)::float AS cost_usd,
                   EXISTS (SELECT 1 FROM gold_visibility g WHERE g.run_id = r.run_id)
                       AS diagnosed
            FROM bronze_runs r LEFT JOIN bronze_responses b USING (run_id)
            GROUP BY r.run_id ORDER BY r.started_at DESC LIMIT %s
            """,
            (limit,),
        )
    )


def list_responses(
    conn: psycopg.Connection, run_id: str, limit: int = 200, parser_version: str = "v1"
) -> list[dict[str, Any]]:
    """Answers of a run with the prompt and which brands each answer mentions."""
    return _rows(
        conn.execute(
            """
            SELECT b.response_id::text, b.repeat_no, b.provider, p.prompt_id, p.text AS prompt,
                   p.category, p.intent, b.answer_text, b.error, b.latency_ms,
                   b.cost_usd::float,
                   coalesce((
                       SELECT jsonb_agg(jsonb_build_object('url', c.url, 'domain', c.domain)
                                        ORDER BY c.position)
                       FROM silver_citations c
                       WHERE c.response_id = b.response_id AND c.parser_version = %s
                   ), '[]'::jsonb) AS citations,
                   coalesce((
                       SELECT jsonb_agg(jsonb_build_object(
                                  'brand', br.name, 'is_target', br.is_target,
                                  'rank', m.rank_in_list, 'sentiment', m.sentiment,
                                  'recommended', m.is_recommended)
                              ORDER BY br.is_target DESC, br.name)
                       FROM silver_brand_mentions m JOIN brands br USING (brand_id)
                       WHERE m.response_id = b.response_id AND m.mentioned
                         AND m.parser_version = %s
                   ), '[]'::jsonb) AS mentions
            FROM bronze_responses b JOIN prompts p USING (prompt_id)
            WHERE b.run_id = %s
            ORDER BY p.prompt_id, b.repeat_no LIMIT %s
            """,
            (parser_version, parser_version, run_id, limit),
        )
    )


def list_prompts(conn: psycopg.Connection) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            "SELECT prompt_id, text, category, intent, panel_version FROM prompts "
            "ORDER BY prompt_id"
        )
    )


def list_brands(conn: psycopg.Connection) -> list[dict[str, Any]]:
    return _rows(
        conn.execute("SELECT brand_id, name, is_target, aliases FROM brands ORDER BY brand_id")
    )


def list_custom_questions(conn: psycopg.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Questions users typed in, newest first, with how often and when they were asked."""
    return _rows(
        conn.execute(
            """
            SELECT p.prompt_id, p.text, p.category, p.created_at,
                   count(DISTINCT b.run_id) AS n_runs, max(b.created_at) AS last_asked
            FROM prompts p LEFT JOIN bronze_responses b USING (prompt_id)
            WHERE p.panel_version = 'custom'
            GROUP BY p.prompt_id ORDER BY max(b.created_at) DESC NULLS LAST LIMIT %s
            """,
            (limit,),
        )
    )
