"""Read-only queries and small pure helpers behind the overview dashboard (app/Home.py)."""

from __future__ import annotations

from typing import Any

import psycopg


def _rows(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def visibility_history(conn: psycopg.Connection) -> list[dict]:
    """Overall ('ALL') metrics for every diagnosed baseline run, oldest first."""
    return _rows(
        conn.execute(
            """
            SELECT r.run_id::text, r.provider, r.started_at, b.name AS brand, b.is_target,
                   g.n_responses, g.mention_rate::float, g.share_of_voice::float,
                   g.avg_rank::float, g.citation_share::float, g.positive_rate::float
            FROM gold_visibility g
            JOIN bronze_runs r USING (run_id) JOIN brands b USING (brand_id)
            WHERE g.category = 'ALL' AND g.metric_version = 'v1' AND r.run_type = 'baseline'
            ORDER BY r.started_at, b.name
            """
        )
    )


def category_matrix(conn: psycopg.Connection) -> list[dict]:
    """Mention rate by brand x category for the latest diagnosed baseline run per provider."""
    return _rows(
        conn.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (r.provider) r.run_id, r.provider
                FROM bronze_runs r
                WHERE r.run_type = 'baseline'
                  AND EXISTS (SELECT 1 FROM gold_visibility g WHERE g.run_id = r.run_id)
                ORDER BY r.provider, r.started_at DESC
            )
            SELECT l.provider, b.name AS brand, b.is_target, g.category, g.n_responses,
                   g.mention_rate::float
            FROM latest l JOIN gold_visibility g USING (run_id) JOIN brands b USING (brand_id)
            WHERE g.category <> 'ALL' AND g.metric_version = 'v1'
            """
        )
    )


def ops_stats(conn: psycopg.Connection) -> list[dict]:
    return _rows(
        conn.execute(
            """
            SELECT r.run_id::text, r.provider, r.run_type, r.status, r.started_at,
                   count(b.response_id) AS calls,
                   count(b.response_id) FILTER (WHERE b.error IS NOT NULL) AS errors,
                   sum(b.cost_usd)::float AS cost_usd, avg(b.latency_ms)::float AS avg_latency_ms
            FROM bronze_runs r LEFT JOIN bronze_responses b USING (run_id)
            GROUP BY r.run_id ORDER BY r.started_at DESC LIMIT 30
            """
        )
    )


def pipeline_counts(conn: psycopg.Connection) -> dict[str, int]:
    queries = {
        "runs": "SELECT count(*) FROM bronze_runs",
        "answers": "SELECT count(*) FROM bronze_responses WHERE error IS NULL",
        "opportunities": "SELECT count(*) FROM opportunities",
        "recs_approved": "SELECT count(*) FROM recommendations WHERE status = 'approved'",
        "drafts": "SELECT count(*) FROM content_variants",
        "drafts_approved": "SELECT count(*) FROM content_variants WHERE status = 'approved'",
        "experiments_done": "SELECT count(*) FROM experiments WHERE status = 'done'",
        "kb_chunks": "SELECT count(*) FROM kb_chunks",
        "migrations": "SELECT count(*) FROM schema_migrations",
    }
    out = {}
    for key, sql in queries.items():
        try:
            out[key] = conn.execute(sql).fetchone()[0]
        except psycopg.Error:  # table missing: a migration has not been applied yet
            conn.rollback()
            out[key] = -1
    return out


def top_opportunities(conn: psycopg.Connection, limit: int = 5) -> list[dict]:
    return _rows(
        conn.execute(
            """
            SELECT o.title, o.gap_type, o.priority_score::float, o.effort, r.status AS review
            FROM opportunities o LEFT JOIN recommendations r USING (opportunity_id)
            ORDER BY o.priority_score DESC NULLS LAST LIMIT %s
            """,
            (limit,),
        )
    )


# ---------------------------------------------------------------- pure helpers (tested)


def kpi_deltas(history: list[dict], metric: str = "mention_rate") -> list[dict]:
    """Per provider: target brand's latest value and change vs that provider's previous run."""
    out = []
    target_rows = [h for h in history if h["is_target"]]
    for provider in sorted({h["provider"] for h in target_rows}):
        rows = sorted((h for h in target_rows if h["provider"] == provider),
                      key=lambda h: h["started_at"])  # fmt: skip
        latest = rows[-1]
        prev = rows[-2] if len(rows) > 1 else None
        value = latest.get(metric)
        delta = None
        if prev and value is not None and prev.get(metric) is not None:
            delta = round(value - prev[metric], 4)
        out.append({"provider": provider, "brand": latest["brand"], "value": value,
                    "delta": delta, "n_responses": latest["n_responses"]})  # fmt: skip
    return out


def leader_by_provider(history: list[dict], metric: str = "mention_rate") -> dict[str, str]:
    """Which brand leads on `metric` in each provider's latest run."""
    leaders = {}
    for provider in {h["provider"] for h in history}:
        rows = [h for h in history if h["provider"] == provider]
        last = max(h["started_at"] for h in rows)
        latest = [h for h in rows if h["started_at"] == last and h.get(metric) is not None]
        if latest:
            leaders[provider] = max(latest, key=lambda h: h[metric])["brand"]
    return leaders
