"""Database access for the experimentation lab."""

from __future__ import annotations

from typing import Any, Protocol

import psycopg

from src.experimentation.models import BaselineRun, Counts, CreateExperimentInput, ResultRow


class ExperimentRepository(Protocol):
    def load_run(self, run_id: str) -> BaselineRun: ...
    def opportunity_prompt_ids(self, opportunity_id: str) -> list[str]: ...
    def run_prompt_ids(self, run_id: str) -> list[str]: ...
    def create(self, inp: CreateExperimentInput, prompt_ids: list[str], hypothesis: str) -> str: ...
    def load(self, experiment_id: str) -> dict[str, Any]: ...
    def set_retest(self, experiment_id: str, retest_run_id: str) -> None: ...
    def counts(self, run_id: str, prompt_ids: list[str]) -> dict[int, Counts]: ...
    def save_results(self, experiment_id: str, rows: list[ResultRow]) -> None: ...


class PostgresExperimentRepository:
    def __init__(self, conn: psycopg.Connection, parser_version: str = "v1") -> None:
        self.conn = conn
        self.parser_version = parser_version

    def load_run(self, run_id: str) -> BaselineRun:
        row = self.conn.execute(
            "SELECT run_id::text, panel_version, provider FROM bronze_runs WHERE run_id = %s",
            (run_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Run {run_id} not found")
        return BaselineRun(run_id=row[0], panel_version=row[1], provider=row[2])

    def opportunity_prompt_ids(self, opportunity_id: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT b.prompt_id FROM opportunities o
            JOIN bronze_responses b ON b.response_id = ANY(o.evidence_response_ids)
            WHERE o.opportunity_id = %s ORDER BY 1
            """,
            (opportunity_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def run_prompt_ids(self, run_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT prompt_id FROM bronze_responses WHERE run_id = %s ORDER BY 1",
            (run_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def create(self, inp: CreateExperimentInput, prompt_ids: list[str], hypothesis: str) -> str:
        row = self.conn.execute(
            """
            INSERT INTO experiments (variant_id, hypothesis, baseline_run_id, prompt_ids, status,
                                     design, opportunity_id, created_by)
            VALUES (%s, %s, %s, %s, 'planned', %s, %s, %s) RETURNING experiment_id
            """,
            (
                inp.variant_id,
                hypothesis,
                inp.baseline_run_id,
                prompt_ids,
                inp.design,
                inp.opportunity_id,
                inp.created_by,
            ),  # fmt: skip
        ).fetchone()
        self.conn.commit()
        return str(row[0])

    def load(self, experiment_id: str) -> dict[str, Any]:
        cur = self.conn.execute(
            """
            SELECT experiment_id::text, baseline_run_id::text, retest_run_id::text, prompt_ids,
                   status, design, hypothesis
            FROM experiments WHERE experiment_id = %s
            """,
            (experiment_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Experiment {experiment_id} not found")
        return dict(zip([d.name for d in cur.description], row, strict=True))

    def set_retest(self, experiment_id: str, retest_run_id: str) -> None:
        self.conn.execute(
            "UPDATE experiments SET retest_run_id = %s, status = 'running' "
            "WHERE experiment_id = %s",
            (retest_run_id, experiment_id),
        )
        self.conn.commit()

    def counts(self, run_id: str, prompt_ids: list[str]) -> dict[int, Counts]:
        rows = self.conn.execute(
            """
            SELECT m.brand_id, count(*) FILTER (WHERE m.mentioned), count(*)
            FROM silver_brand_mentions m JOIN bronze_responses b USING (response_id)
            WHERE m.run_id = %s AND m.parser_version = %s AND b.prompt_id = ANY(%s)
            GROUP BY m.brand_id
            """,
            (run_id, self.parser_version, prompt_ids),
        ).fetchall()
        return {r[0]: Counts(x=r[1], n=r[2]) for r in rows}

    def save_results(self, experiment_id: str, rows: list[ResultRow]) -> None:
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO experiment_results
                  (experiment_id, brand_id, metric, baseline_value, retest_value, delta, p_value,
                   n_baseline, n_retest, ci_low, ci_high, interpretation)
                VALUES (%(experiment_id)s, %(brand_id)s, %(metric)s, %(baseline_value)s,
                        %(retest_value)s, %(delta)s, %(p_value)s, %(n_baseline)s,
                        %(n_retest)s, %(ci_low)s, %(ci_high)s, %(interpretation)s)
                ON CONFLICT (experiment_id, brand_id, metric) DO UPDATE
                SET baseline_value = EXCLUDED.baseline_value, retest_value = EXCLUDED.retest_value,
                    delta = EXCLUDED.delta, p_value = EXCLUDED.p_value,
                    n_baseline = EXCLUDED.n_baseline, n_retest = EXCLUDED.n_retest,
                    ci_low = EXCLUDED.ci_low, ci_high = EXCLUDED.ci_high,
                    interpretation = EXCLUDED.interpretation, computed_at = now()
                """,
                [r.model_dump() for r in rows],
            )
            cur.execute(
                "UPDATE experiments SET status = 'done', completed_at = now() "
                "WHERE experiment_id = %s",
                (experiment_id,),
            )
        self.conn.commit()


def _rows(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def list_experiments(conn: psycopg.Connection) -> list[dict]:
    return _rows(
        conn.execute(
            """
            SELECT e.experiment_id::text, e.status, e.design, e.hypothesis,
                   cardinality(e.prompt_ids) AS n_prompts, e.baseline_run_id::text,
                   e.retest_run_id::text, v.title AS variant, v.status AS variant_status,
                   e.created_by, e.created_at, e.completed_at
            FROM experiments e LEFT JOIN content_variants v USING (variant_id)
            ORDER BY e.created_at DESC
            """
        )
    )


def load_results(conn: psycopg.Connection, experiment_id: str) -> list[dict]:
    return _rows(
        conn.execute(
            """
            SELECT b.name AS brand, b.is_target, r.baseline_value::float, r.retest_value::float,
                   r.delta::float, r.ci_low::float, r.ci_high::float, r.p_value::float,
                   r.n_baseline, r.n_retest, r.interpretation
            FROM experiment_results r JOIN brands b USING (brand_id)
            WHERE r.experiment_id = %s ORDER BY b.is_target DESC, b.name
            """,
            (experiment_id,),
        )
    )
