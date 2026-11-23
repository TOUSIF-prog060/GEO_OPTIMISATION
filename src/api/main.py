"""FastAPI backend for the Next.js dashboard.

Run:  uvicorn src.api.main:app --port 8000 --reload
Reads call the existing query helpers; slow or billed work runs as a background job
(see src/api/jobs.py) and is written to the database by the engines themselves.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from typing import Any, Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from psycopg.types.numeric import FloatLoader
from pydantic import BaseModel, Field

from src import reporting, services
from src.api import queries
from src.api.jobs import Job, JobManager, ProgressFn
from src.config import ROOT_DIR, Settings, get_settings
from src.copilot import ingest_knowledge
from src.copilot.knowledge import load_docs
from src.copilot.repository import (
    PostgresCopilotRepository,
    kb_stats,
    list_variants,
    load_chunks,
)
from src.db import check_connection, get_conn
from src.diagnostics.repository import (
    PostgresDiagnosticsRepository,
    load_gold_accuracy,
    load_product_mention_counts,
    load_repeatability,
    load_source_share,
    load_visibility,
)
from src.diagnostics.validation import evaluate, load_labels, load_system_mentions
from src.discovery import DiscoveryInput, plan_discovery
from src.discovery.models import CUSTOM_PANEL, PromptRow
from src.discovery.panel import REFERENCE_DIR, custom_prompt, load_db_prompts, load_panel
from src.discovery.providers import get_api_key
from src.experimentation.repository import list_experiments, load_results
from src.opportunities.repository import (
    list_opportunities,
    load_evidence,
    review_recommendation,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Beyond the Search Bar API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
jobs = JobManager()


def db() -> Iterator[psycopg.Connection]:
    try:
        conn = get_conn()
    except Exception as exc:
        logger.exception("DB connection failed")
        raise HTTPException(503, f"Database unavailable: {exc}") from exc
    # JSON for the browser: numeric -> float (Decimal would serialise as a string)
    conn.adapters.register_loader("numeric", FloatLoader)
    with conn:
        yield conn


def settings_dep() -> Settings:
    return get_settings()


Conn = Depends(db)
Cfg = Depends(settings_dep)


# ---------------------------------------------------------------- status & overview


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def status(settings: Settings = Cfg) -> dict[str, Any]:
    ok, msg = check_connection() if settings.supabase_db_url else (False, "SUPABASE_DB_URL not set")
    p = settings.project
    return {
        "db": {"ok": ok, "message": msg[:120]},
        "project": {
            "name": p.project,
            "market": p.market,
            "target": p.target.name,
            "competitors": [b.name for b in p.competitors],
        },  # fmt: skip
        "providers": [
            {
                "name": c.name,
                "model": c.model,
                "enabled": c.enabled,
                "has_key": bool(get_api_key(settings, c.name)),
            }  # fmt: skip
            for c in p.providers
        ],
        "analysis": {"model": p.analysis.model, "has_key": bool(settings.openai_api_key)},
    }


@app.get("/api/overview")
def overview(conn: psycopg.Connection = Conn) -> dict[str, Any]:
    history = reporting.visibility_history(conn)
    return {
        "counts": reporting.pipeline_counts(conn),
        "history": history,
        "kpis": reporting.kpi_deltas(history),
        "sov": reporting.kpi_deltas(history, "share_of_voice"),
        "leaders": reporting.leader_by_provider(history),
        "categories": reporting.category_matrix(conn),
        "top_opportunities": reporting.top_opportunities(conn, 6),
        "ops": reporting.ops_stats(conn),
    }


# ---------------------------------------------------------------- discovery


@app.get("/api/panels")
def panels() -> list[dict[str, Any]]:
    out = []
    for path in sorted(REFERENCE_DIR.glob("prompt_panel_*.csv")):
        version = path.stem.removeprefix("prompt_panel_")
        rows = load_panel(path)
        out.append({"version": version, "prompts": [r.model_dump() for r in rows]})
    return out


class DiscoveryBody(BaseModel):
    panel_version: str = "v0"
    providers: list[str] | None = None
    repeats: int = Field(1, ge=1, le=5)
    limit: int | None = Field(None, ge=1)
    prompt_ids: list[str] | None = None


def _discovery_input(body: DiscoveryBody) -> DiscoveryInput:
    return DiscoveryInput(panel_version=body.panel_version, providers=body.providers,
                          repeats=body.repeats, limit=body.limit,
                          prompt_ids=body.prompt_ids)  # fmt: skip


@app.post("/api/discovery/plan")
def discovery_plan(body: DiscoveryBody, settings: Settings = Cfg) -> dict[str, Any]:
    try:
        return plan_discovery(_discovery_input(body), settings).model_dump()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/discovery")
def start_discovery(body: DiscoveryBody, settings: Settings = Cfg) -> Job:
    try:
        plan = plan_discovery(_discovery_input(body), settings)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if plan.missing_keys:
        raise HTTPException(400, f"Missing API key(s): {plan.missing_keys}")

    def run(progress: ProgressFn) -> dict[str, Any]:
        def on_progress(provider: str, done: int, total: int) -> None:
            progress({"provider": provider, "done": done, "total": total})

        ids = services.discover(body.panel_version, body.providers, body.repeats, body.limit,
                                body.prompt_ids, on_progress=on_progress)  # fmt: skip
        return {"run_ids": ids}

    return jobs.submit("discovery", body.model_dump(), run)


class AskBody(BaseModel):
    """Questions typed in by the user, and/or earlier custom questions to ask again."""

    questions: list[str] = Field(default_factory=list, max_length=10)
    prompt_ids: list[str] = Field(default_factory=list, max_length=20)
    category: str = Field("custom", max_length=40)
    providers: list[str] | None = None
    repeats: int = Field(1, ge=1, le=5)


def _custom_prompts(body: AskBody, conn: psycopg.Connection) -> list[PromptRow]:
    rows: dict[str, PromptRow] = {}
    for q in body.questions:
        if len(q.strip()) < 5:
            raise HTTPException(400, f"Question too short: {q!r}")
        if len(q) > 600:
            raise HTTPException(400, "Questions are limited to 600 characters.")
        p = custom_prompt(q, category=body.category.strip().lower() or "custom")
        rows[p.prompt_id] = p
    if body.prompt_ids:
        try:
            for p in load_db_prompts(conn, body.prompt_ids):
                rows[p.prompt_id] = p
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    if not rows:
        raise HTTPException(400, "Type at least one question.")
    return list(rows.values())


@app.post("/api/ask/plan")
def ask_plan(
    body: AskBody, settings: Settings = Cfg, conn: psycopg.Connection = Conn
) -> dict[str, Any]:
    prompts = _custom_prompts(body, conn)
    inp = DiscoveryInput(panel_version=CUSTOM_PANEL, providers=body.providers,
                         repeats=body.repeats, custom_prompts=prompts)  # fmt: skip
    try:
        return plan_discovery(inp, settings).model_dump()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs/ask")
def start_ask(body: AskBody, settings: Settings = Cfg, conn: psycopg.Connection = Conn) -> Job:
    """Ask custom questions (billed), then measure the answers (free). Runs are 'adhoc', so
    they never mix into the panel-based headline numbers."""
    prompts = _custom_prompts(body, conn)
    inp = DiscoveryInput(panel_version=CUSTOM_PANEL, providers=body.providers,
                         repeats=body.repeats, custom_prompts=prompts)  # fmt: skip
    try:
        plan = plan_discovery(inp, settings)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if plan.missing_keys:
        raise HTTPException(400, f"Missing API key(s): {plan.missing_keys}")

    def run(progress: ProgressFn) -> dict[str, Any]:
        def on_progress(provider: str, done: int, total: int) -> None:
            progress({"provider": provider, "done": done, "total": total, "stage": "asking"})

        ids = services.discover(CUSTOM_PANEL, body.providers, body.repeats, run_type="adhoc",
                                custom_prompts=prompts, on_progress=on_progress)  # fmt: skip
        for i, run_id in enumerate(ids, 1):
            progress({"stage": "measuring", "done": i, "total": len(ids)})
            services.diagnose_run(run_id)
        return {"run_ids": ids, "prompt_ids": [p.prompt_id for p in prompts]}

    return jobs.submit("ask", body.model_dump(), run)


@app.get("/api/custom-questions")
def custom_questions(conn: psycopg.Connection = Conn) -> list[dict[str, Any]]:
    return queries.list_custom_questions(conn)


@app.get("/api/ask/answers")
def ask_answers(run_ids: str, conn: psycopg.Connection = Conn) -> list[dict[str, Any]]:
    """Answers of several runs (one per engine), for the side-by-side view."""
    out: list[dict[str, Any]] = []
    for run_id in [r for r in run_ids.split(",") if r][:5]:
        out.extend(queries.list_responses(conn, run_id, 200))
    return out


# ---------------------------------------------------------------- runs & diagnostics


@app.get("/api/runs")
def runs(conn: psycopg.Connection = Conn) -> list[dict[str, Any]]:
    return queries.list_runs_full(conn)


@app.get("/api/runs/{run_id}")
def run(run_id: str, conn: psycopg.Connection = Conn) -> dict[str, Any]:
    row = queries.run_detail(conn, run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    return row


@app.get("/api/runs/{run_id}/visibility")
def visibility(run_id: str, conn: psycopg.Connection = Conn) -> dict[str, Any]:
    return {
        "visibility": load_visibility(conn, run_id),
        "sources": load_source_share(conn, run_id),
        "repeatability": load_repeatability(conn, run_id),
        "accuracy": load_gold_accuracy(conn, run_id),
        "products": load_product_mention_counts(conn, run_id),
    }


@app.get("/api/runs/{run_id}/responses")
def responses(run_id: str, limit: int = 300, conn: psycopg.Connection = Conn) -> list[dict]:
    return queries.list_responses(conn, run_id, limit)


class DiagnoseBody(BaseModel):
    run_id: str
    label_sentiment: bool = False
    check_accuracy: bool = False


@app.post("/api/jobs/diagnose")
def start_diagnose(body: DiagnoseBody, settings: Settings = Cfg) -> Job:
    if (body.label_sentiment or body.check_accuracy) and not settings.openai_api_key:
        raise HTTPException(400, "LLM labelling needs OPENAI_API_KEY.")

    def run(progress: ProgressFn) -> dict[str, Any]:
        return services.diagnose_run(body.run_id, body.label_sentiment, body.check_accuracy)

    return jobs.submit("diagnose", body.model_dump(), run)


# ---------------------------------------------------------------- opportunities


@app.get("/api/opportunities")
def opportunities(run_id: str | None = None, conn: psycopg.Connection = Conn) -> list[dict]:
    return list_opportunities(conn, run_id)


@app.get("/api/opportunities/{opportunity_id}/evidence")
def evidence(opportunity_id: str, conn: psycopg.Connection = Conn) -> list[dict]:
    return load_evidence(conn, opportunity_id)


class RunBody(BaseModel):
    run_id: str


@app.post("/api/jobs/opportunities")
def start_opportunities(body: RunBody) -> Job:
    def run(progress: ProgressFn) -> dict[str, Any]:
        found = services.opportunities_for(body.run_id)
        return {"n_opportunities": len(found)}

    return jobs.submit("opportunities", body.model_dump(), run)


class ReviewBody(BaseModel):
    status: Literal["approved", "rejected", "proposed", "draft"]
    reviewer: str = Field(min_length=1, max_length=16)
    notes: str = ""


@app.post("/api/recommendations/{recommendation_id}/review")
def review_rec(recommendation_id: str, body: ReviewBody,
               conn: psycopg.Connection = Conn) -> dict[str, str]:  # fmt: skip
    try:
        review_recommendation(conn, recommendation_id, body.status, body.reviewer, body.notes)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": body.status}


# ---------------------------------------------------------------- copilot


@app.get("/api/knowledge")
def knowledge(conn: psycopg.Connection = Conn) -> dict[str, Any]:
    try:
        local = [{"doc_id": d.doc_id, "title": d.title, "source_url": d.source_url,
                  "verified_at": str(d.verified_at)} for d in load_docs()]  # fmt: skip
        error = None
    except ValueError as exc:
        local, error = [], str(exc)
    return {"stats": kb_stats(conn), "local_docs": local, "error": error}


@app.post("/api/jobs/ingest")
def start_ingest(settings: Settings = Cfg) -> Job:
    if not settings.openai_api_key:
        raise HTTPException(400, "Embedding needs OPENAI_API_KEY.")

    def run(progress: ProgressFn) -> Any:
        with get_conn() as conn:
            return ingest_knowledge(settings, PostgresCopilotRepository(conn)).model_dump()

    return jobs.submit("ingest", {}, run)


@app.get("/api/variants")
def variants(opportunity_id: str | None = None, conn: psycopg.Connection = Conn) -> list[dict]:
    return list_variants(conn, opportunity_id)


@app.get("/api/chunks")
def chunks(ids: str, conn: psycopg.Connection = Conn) -> list[dict]:
    try:
        chunk_ids = [int(x) for x in ids.split(",") if x]
    except ValueError as exc:
        raise HTTPException(400, "ids must be comma-separated integers") from exc
    return load_chunks(conn, chunk_ids)


class OpportunityBody(BaseModel):
    opportunity_id: str


@app.post("/api/jobs/draft")
def start_draft(body: OpportunityBody, settings: Settings = Cfg) -> Job:
    if not settings.openai_api_key:
        raise HTTPException(400, "Drafting needs OPENAI_API_KEY.")

    def run(progress: ProgressFn) -> dict[str, Any]:
        return services.draft_for(body.opportunity_id)

    return jobs.submit("draft", body.model_dump(), run)


@app.post("/api/variants/{variant_id}/review")
def review_draft(variant_id: str, body: ReviewBody) -> dict[str, str]:
    try:
        services.review(variant_id, body.status, body.reviewer, body.notes)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": body.status}


# ---------------------------------------------------------------- agent


@app.get("/api/agent/runs")
def agent_runs() -> list[dict]:
    from src.agent.tools import list_agent_runs

    return list_agent_runs()


@app.get("/api/agent/runs/{thread_id}")
def agent_run(thread_id: str, settings: Settings = Cfg) -> dict[str, Any]:
    from src.agent import get_run, postgres_checkpointer
    from src.agent.tools import PostgresAgentTools

    with postgres_checkpointer(settings.require("supabase_db_url")) as cp:
        st, pending, values = get_run(PostgresAgentTools(), cp, thread_id)
    return {"thread_id": thread_id, "status": st, "pending": pending, "values": values}


class AgentBody(BaseModel):
    run_ids: list[str] | None = None
    panel_version: str = "v0"
    providers: list[str] | None = None
    limit: int | None = Field(5, ge=1)
    repeats: int = Field(1, ge=1, le=5)
    max_drafts: int = Field(3, ge=1, le=10)
    label_sentiment: bool = False
    check_accuracy: bool = False


@app.post("/api/jobs/agent")
def start_agent(body: AgentBody, settings: Settings = Cfg) -> Job:
    from src.agent import postgres_checkpointer, start_run
    from src.agent.tools import PostgresAgentTools

    params = body.model_dump(exclude_none=True)

    def run(progress: ProgressFn) -> dict[str, Any]:
        with postgres_checkpointer(settings.require("supabase_db_url")) as cp:
            tid, st, pending, _ = start_run(PostgresAgentTools(), cp, params)
        return {"thread_id": tid, "status": st, "awaiting_review": bool(pending)}

    return jobs.submit("agent", params, run)


class ResumeBody(BaseModel):
    approved: list[str] = []
    rejected: list[str] = []
    reviewer: str = Field(min_length=1, max_length=16)
    notes: str = ""


@app.post("/api/jobs/agent/{thread_id}/resume")
def resume_agent(thread_id: str, body: ResumeBody, settings: Settings = Cfg) -> Job:
    from src.agent import postgres_checkpointer, resume_run
    from src.agent.tools import PostgresAgentTools

    def run(progress: ProgressFn) -> dict[str, Any]:
        with postgres_checkpointer(settings.require("supabase_db_url")) as cp:
            st, pending, _ = resume_run(PostgresAgentTools(), cp, thread_id, body.model_dump())
        return {"thread_id": thread_id, "status": st}

    return jobs.submit("agent_resume", {"thread_id": thread_id, **body.model_dump()}, run)


# ---------------------------------------------------------------- experiments


@app.get("/api/experiments")
def experiments(conn: psycopg.Connection = Conn) -> list[dict]:
    return list_experiments(conn)


@app.get("/api/experiments/{experiment_id}/results")
def experiment_results(experiment_id: str, conn: psycopg.Connection = Conn) -> list[dict]:
    return load_results(conn, experiment_id)


class ExperimentBody(BaseModel):
    baseline_run_id: str
    design: Literal["content_variant", "repeat_baseline"] = "content_variant"
    variant_id: str | None = None
    opportunity_id: str | None = None
    created_by: str = "user"


@app.post("/api/experiments")
def plan_experiment(body: ExperimentBody) -> dict[str, str]:
    try:
        eid = services.plan_experiment(
            body.variant_id,
            body.opportunity_id,
            body.baseline_run_id,
            body.created_by,
            body.design,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"experiment_id": eid}


class RetestBody(BaseModel):
    repeats: int = Field(3, ge=1, le=5)


@app.post("/api/jobs/experiments/{experiment_id}/retest")
def start_retest(experiment_id: str, body: RetestBody) -> Job:
    def run(progress: ProgressFn) -> Any:
        return services.retest(experiment_id, body.repeats).model_dump()

    return jobs.submit("retest", {"experiment_id": experiment_id, **body.model_dump()}, run)


# ---------------------------------------------------------------- validation


@app.get("/api/validation")
def validation(conn: psycopg.Connection = Conn) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT s.sample_version, count(DISTINCT s.response_id) AS n_responses,
               (SELECT count(*) FROM validation_labels l
                WHERE l.sample_version = s.sample_version) AS n_labels
        FROM validation_samples s GROUP BY s.sample_version ORDER BY s.sample_version
        """
    )
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


@app.get("/api/validation/{sample_version}")
def validation_report(sample_version: str, conn: psycopg.Connection = Conn) -> dict | None:
    labels = load_labels(conn, sample_version)
    if not labels:
        return None
    system = load_system_mentions(conn, sample_version)
    brand_ids = {b.name: b.brand_id for b in PostgresDiagnosticsRepository(conn).load_brands()}
    return evaluate(sample_version, labels, system, brand_ids).model_dump()


# ---------------------------------------------------------------- PDF reports

REPORT_DIRS = {"run_report": ROOT_DIR / "reports" / "runs",
               "evaluation_report": ROOT_DIR / "reports" / "evals"}  # fmt: skip
_REPORT_NAME = re.compile(r"^(run_report|evaluation_report)_[A-Za-z0-9_-]+\.(pdf|html)$")


class ReportBody(BaseModel):
    kind: Literal["run", "evaluation"]
    run_id: str | None = None


@app.post("/api/jobs/report")
def start_report(body: ReportBody) -> Job:
    """Build a PDF report in the background; download it from /api/reports/{file}."""
    if body.kind == "run" and not body.run_id:
        raise HTTPException(400, "run_id is required for a run report")

    def run(progress: ProgressFn) -> dict[str, Any]:
        if body.kind == "run":
            from src.run_report import build_run_report

            path = build_run_report(body.run_id)
        else:
            from evals.report_pdf import build_report

            path = build_report()
        return {"file": path.name, "format": path.suffix.lstrip(".")}

    return jobs.submit("report", body.model_dump(), run)


@app.get("/api/reports")
def list_reports() -> list[dict[str, Any]]:
    out = []
    for prefix, folder in REPORT_DIRS.items():
        for f in folder.glob(f"{prefix}_*.pdf"):
            st = f.stat()
            out.append({"file": f.name, "kind": prefix.removesuffix("_report"),
                        "size_kb": round(st.st_size / 1024), "created": st.st_mtime})  # fmt: skip
    return sorted(out, key=lambda r: r["created"], reverse=True)[:30]


@app.get("/api/reports/{name}")
def download_report(name: str) -> FileResponse:
    m = _REPORT_NAME.match(name)
    if not m:
        raise HTTPException(400, "Not a report file name")
    path = (REPORT_DIRS[m.group(1)] / name).resolve()
    if path.parent != REPORT_DIRS[m.group(1)].resolve() or not path.is_file():
        raise HTTPException(404, "Report not found")
    media = "application/pdf" if name.endswith(".pdf") else "text/html"
    return FileResponse(path, media_type=media, filename=name)


# ---------------------------------------------------------------- jobs


@app.get("/api/jobs")
def list_jobs() -> list[Job]:
    return jobs.list()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> Job:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found (the API may have restarted)")
    return job


__all__ = ["app"]
