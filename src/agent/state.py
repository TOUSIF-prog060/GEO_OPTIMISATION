"""Agent state and the tool interface the agent uses to call the engines."""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol, TypedDict


class DraftSummary(TypedDict):
    variant_id: str
    opportunity_id: str
    title: str
    grounded: bool


class AgentState(TypedDict, total=False):
    # parameters
    panel_version: str
    providers: list[str] | None
    repeats: int
    limit: int | None
    max_drafts: int
    label_sentiment: bool
    check_accuracy: bool
    # progress (IDs only; data lives in the database)
    run_ids: list[str]
    opportunity_ids: list[str]
    drafts: list[DraftSummary]
    approved_variant_ids: list[str]
    rejected_variant_ids: list[str]
    experiment_ids: list[str]
    report: dict[str, Any]
    # append-only trace
    log: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]


def event(node: str, message: str, **data: Any) -> dict[str, Any]:
    return {"at": datetime.now(UTC).isoformat(timespec="seconds"), "node": node,
            "message": message, **data}  # fmt: skip


class AgentTools(Protocol):
    """Each method wraps one engine call. The agent never touches SQL or APIs directly."""

    def discover(self, panel_version: str, providers: list[str] | None, repeats: int,
                 limit: int | None) -> list[str]: ...  # fmt: skip
    def diagnose(self, run_id: str, label_sentiment: bool, check_accuracy: bool) -> dict: ...
    def find_opportunities(self, run_id: str) -> list[tuple[str, float]]: ...
    def draft(self, opportunity_id: str) -> DraftSummary: ...
    def review(self, variant_id: str, status: str, reviewer: str, notes: str) -> None: ...
    def plan_experiment(self, variant_id: str, opportunity_id: str, baseline_run_id: str,
                        created_by: str) -> str: ...  # fmt: skip
    def record(self, thread_id: str, status: str, last_node: str, summary: dict) -> None: ...
