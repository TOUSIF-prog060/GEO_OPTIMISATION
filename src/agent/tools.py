"""Production AgentTools: each method delegates to src.services (engines + Postgres)."""

from __future__ import annotations

from psycopg.types.json import Jsonb

from src import services
from src.agent.state import DraftSummary
from src.db import get_conn


class PostgresAgentTools:
    def discover(self, panel_version, providers, repeats, limit) -> list[str]:
        return services.discover(panel_version, providers, repeats, limit)

    def diagnose(self, run_id, label_sentiment, check_accuracy) -> dict:
        out = services.diagnose_run(run_id, label_sentiment, check_accuracy)
        return {k: out[k] for k in ("n_responses", "n_mentions", "n_citations") if k in out}

    def find_opportunities(self, run_id) -> list[tuple[str, float]]:
        return services.opportunities_for(run_id)

    def draft(self, opportunity_id) -> DraftSummary:
        return services.draft_for(opportunity_id)  # type: ignore[return-value]

    def review(self, variant_id, status, reviewer, notes) -> None:
        services.review(variant_id, status, reviewer, notes)

    def plan_experiment(self, variant_id, opportunity_id, baseline_run_id, created_by) -> str:
        return services.plan_experiment(variant_id, opportunity_id, baseline_run_id, created_by)

    def record(self, thread_id, status, last_node, summary) -> None:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO agent_runs (thread_id, status, last_node, summary)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (thread_id) DO UPDATE
                SET status = EXCLUDED.status, last_node = EXCLUDED.last_node,
                    summary = EXCLUDED.summary, updated_at = now()
                """,
                (thread_id, status, last_node, Jsonb(summary)),
            )
            conn.commit()


def list_agent_runs(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT thread_id, status, last_node, summary, created_at, updated_at "
            "FROM agent_runs ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
