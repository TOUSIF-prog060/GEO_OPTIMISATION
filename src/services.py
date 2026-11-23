"""Wire each engine to Postgres. The agent, the experimentation lab, scripts and UI call
these instead of repeating connection and repository setup."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.config import Settings, get_settings
from src.copilot import DraftInput, draft_content
from src.copilot.repository import PostgresCopilotRepository, review_variant
from src.db import get_conn
from src.diagnostics import (
    AccuracyInput,
    ClassifyInput,
    DiagnoseInput,
    check_accuracy,
    classify_mentions,
    diagnose,
)
from src.diagnostics.repository import PostgresDiagnosticsRepository, sync_reference
from src.discovery import DiscoveryInput, run_discovery
from src.discovery.panel import load_panel, panel_path, sync_brands, sync_prompts
from src.discovery.repository import PostgresRunRepository
from src.experimentation import CreateExperimentInput, RetestInput, create_experiment, run_retest
from src.experimentation.repository import PostgresExperimentRepository
from src.opportunities import OpportunityInput, find_opportunities
from src.opportunities.repository import PostgresOpportunityRepository


def discover(
    panel_version: str,
    providers: list[str] | None = None,
    repeats: int = 1,
    limit: int | None = None,
    prompt_ids: list[str] | None = None,
    run_type: str = "baseline",
    settings: Settings | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> list[str]:
    settings = settings or get_settings()
    inp = DiscoveryInput(panel_version=panel_version, providers=providers, repeats=repeats,
                         limit=limit, prompt_ids=prompt_ids, run_type=run_type)  # fmt: skip
    with get_conn() as conn:
        sync_brands(conn, settings.project)
        sync_prompts(conn, load_panel(panel_path(panel_version)), panel_version)
        out = run_discovery(inp, settings, PostgresRunRepository(conn), on_progress=on_progress)
    return out.run_ids


def diagnose_run(
    run_id: str, label_sentiment: bool = False, accuracy: bool = False, ref_version: str = "v1"
) -> dict[str, Any]:
    settings = get_settings()
    with get_conn() as conn:
        sync_reference(conn, ref_version)
        repo = PostgresDiagnosticsRepository(conn)
        out = diagnose(DiagnoseInput(run_id=run_id), repo).model_dump()
        if label_sentiment:
            out["labelled"] = classify_mentions(
                ClassifyInput(run_id=run_id), settings, repo
            ).n_classified
        if accuracy and repo.load_facts():
            out["accuracy_checks"] = check_accuracy(
                AccuracyInput(run_id=run_id), settings, repo
            ).n_checks
    return out


def opportunities_for(run_id: str) -> list[tuple[str, float]]:
    with get_conn() as conn:
        repo = PostgresOpportunityRepository(conn)
        out = find_opportunities(OpportunityInput(run_id=run_id), repo)
        rows = conn.execute(
            "SELECT opportunity_id::text, priority_score::float FROM opportunities "
            "WHERE opportunity_id = ANY(%s::uuid[])",
            (out.opportunity_ids,),
        ).fetchall()
    return [(r[0], r[1] or 0.0) for r in rows]


def draft_for(opportunity_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        out = draft_content(DraftInput(opportunity_id=opportunity_id), get_settings(),
                            PostgresCopilotRepository(conn))  # fmt: skip
    return {"variant_id": out.variant_id, "opportunity_id": out.opportunity_id,
            "title": out.title, "grounded": out.grounded}  # fmt: skip


def review(variant_id: str, status: str, reviewer: str, notes: str = "") -> None:
    with get_conn() as conn:
        review_variant(conn, variant_id, status, reviewer, notes)


def plan_experiment(variant_id: str | None, opportunity_id: str | None, baseline_run_id: str,
                    created_by: str = "user", design: str = "content_variant") -> str:  # fmt: skip
    with get_conn() as conn:
        return create_experiment(
            CreateExperimentInput(
                baseline_run_id=baseline_run_id,
                variant_id=variant_id,
                opportunity_id=opportunity_id,
                created_by=created_by,
                design=design,
            ),  # fmt: skip
            PostgresExperimentRepository(conn),
        )


def retest(experiment_id: str, repeats: int = 3):
    def _discover(panel: str, provider: str, prompt_ids: list[str], reps: int) -> str:
        return discover(panel, [provider], reps, prompt_ids=prompt_ids, run_type="retest")[0]

    def _diagnose(run_id: str) -> None:
        diagnose_run(run_id)

    with get_conn() as conn:
        return run_retest(RetestInput(experiment_id=experiment_id, repeats=repeats),
                          PostgresExperimentRepository(conn), _discover, _diagnose)  # fmt: skip
