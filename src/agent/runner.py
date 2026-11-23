"""Start, inspect and resume agent runs (used by the UI and the CLI)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agent.graph import build_graph
from src.agent.state import AgentTools


@contextmanager
def postgres_checkpointer(db_url: str) -> Iterator[Any]:
    """LangGraph checkpoints in Supabase. Creates its tables on first use."""
    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(db_url) as saver:
        saver.setup()
        yield saver


def memory_checkpointer() -> InMemorySaver:
    return InMemorySaver()


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _status(graph, thread_id: str) -> tuple[str, list[dict], dict]:
    snap = graph.get_state(_config(thread_id))
    pending = [i.value for t in snap.tasks for i in (t.interrupts or ())]
    if pending:
        return "awaiting_review", pending, snap.values
    return ("completed" if not snap.next else "running"), [], snap.values


def start_run(tools: AgentTools, checkpointer: Any, params: dict, thread_id: str | None = None):
    """Run until finished or paused for review. Returns (thread_id, status, interrupts, state)."""
    thread_id = thread_id or f"agent-{uuid.uuid4().hex[:12]}"
    graph = build_graph(tools, checkpointer)
    tools.record(thread_id, "running", "start", {"params": params})
    try:
        graph.invoke({**params, "log": [], "errors": []}, _config(thread_id))
    except Exception as exc:
        tools.record(thread_id, "failed", "error", {"error": str(exc)})
        raise
    status, pending, values = _status(graph, thread_id)
    tools.record(thread_id, status, "human_review" if pending else "report",
                 values.get("report") or {"drafts": values.get("drafts", [])})  # fmt: skip
    return thread_id, status, pending, values


def resume_run(tools: AgentTools, checkpointer: Any, thread_id: str, decision: dict):
    """decision = {"approved": [variant_ids], "rejected": [...], "reviewer": "TS", "notes": ""}"""
    graph = build_graph(tools, checkpointer)
    try:
        graph.invoke(Command(resume=decision), _config(thread_id))
    except Exception as exc:
        tools.record(thread_id, "failed", "error", {"error": str(exc)})
        raise
    status, pending, values = _status(graph, thread_id)
    tools.record(thread_id, status, "report", values.get("report") or {})
    return status, pending, values


def get_run(tools: AgentTools, checkpointer: Any, thread_id: str):
    return _status(build_graph(tools, checkpointer), thread_id)
