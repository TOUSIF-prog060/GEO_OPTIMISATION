"""Database access for discovery runs. The runner depends on the `RunRepository`
protocol, so tests can use an in-memory fake instead of Postgres."""

from __future__ import annotations

import logging
from typing import Any, Protocol

import psycopg
from psycopg.types.json import Jsonb

from src.discovery.models import ProviderAnswer

logger = logging.getLogger(__name__)


class RunRepository(Protocol):
    def create_run(
        self,
        *,
        panel_version: str,
        provider: str,
        model: str,
        config_snapshot: dict[str, Any],
        run_type: str,
        notes: str | None,
    ) -> str: ...

    def save_answer(
        self, *, run_id: str, prompt_id: str, repeat_no: int, provider: str, answer: ProviderAnswer
    ) -> str: ...

    def save_error(
        self,
        *,
        run_id: str,
        prompt_id: str,
        repeat_no: int,
        provider: str,
        model: str,
        request: dict[str, Any],
        error: str,
        http_status: int | None,
    ) -> str: ...

    def finish_run(self, run_id: str, status: str) -> None: ...


class PostgresRunRepository:
    """Writes to bronze_runs / bronze_responses. Each write is committed immediately,
    so a crash mid-run keeps everything collected so far."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def create_run(
        self,
        *,
        panel_version: str,
        provider: str,
        model: str,
        config_snapshot: dict[str, Any],
        run_type: str,
        notes: str | None,
    ) -> str:
        row = self.conn.execute(
            """
            INSERT INTO bronze_runs
              (panel_version, provider, model, config_snapshot, run_type, notes)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING run_id
            """,
            (panel_version, provider, model, Jsonb(config_snapshot), run_type, notes),
        ).fetchone()
        self.conn.commit()
        return str(row[0])

    def save_answer(
        self, *, run_id: str, prompt_id: str, repeat_no: int, provider: str, answer: ProviderAnswer
    ) -> str:
        row = self.conn.execute(
            """
            INSERT INTO bronze_responses
              (run_id, prompt_id, repeat_no, provider, model, request, raw_response, answer_text,
               input_tokens, output_tokens, cost_usd, latency_ms, http_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING response_id
            """,
            (
                run_id,
                prompt_id,
                repeat_no,
                provider,
                answer.model,
                Jsonb(answer.request),
                Jsonb(answer.raw),
                answer.answer_text,
                answer.input_tokens,
                answer.output_tokens,
                answer.cost_usd,
                answer.latency_ms,
                answer.http_status,
            ),
        ).fetchone()
        self.conn.commit()
        return str(row[0])

    def save_error(
        self,
        *,
        run_id: str,
        prompt_id: str,
        repeat_no: int,
        provider: str,
        model: str,
        request: dict[str, Any],
        error: str,
        http_status: int | None,
    ) -> str:
        row = self.conn.execute(
            """
            INSERT INTO bronze_responses
              (run_id, prompt_id, repeat_no, provider, model, request, error, http_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING response_id
            """,
            (run_id, prompt_id, repeat_no, provider, model, Jsonb(request), error, http_status),
        ).fetchone()
        self.conn.commit()
        return str(row[0])

    def finish_run(self, run_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE bronze_runs SET status = %s, finished_at = now() WHERE run_id = %s",
            (status, run_id),
        )
        self.conn.commit()


def list_recent_runs(conn: psycopg.Connection, limit: int = 20) -> list[dict[str, Any]]:
    """Runs with response counts and cost, newest first. Used by the UI."""
    cur = conn.execute(
        """
        SELECT r.run_id, r.provider, r.model, r.panel_version, r.run_type, r.status,
               r.started_at, r.finished_at,
               count(b.response_id)                          AS n_responses,
               count(b.response_id) FILTER (WHERE b.error IS NOT NULL) AS n_errors,
               sum(b.cost_usd)                               AS cost_usd
        FROM bronze_runs r
        LEFT JOIN bronze_responses b ON b.run_id = r.run_id
        GROUP BY r.run_id
        ORDER BY r.started_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
