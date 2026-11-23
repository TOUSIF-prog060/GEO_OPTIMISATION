"""LangGraph workflow: discover -> diagnose -> opportunities -> draft -> HUMAN REVIEW
-> plan experiments -> report.

Nodes only call `AgentTools` (thin wrappers around the engine functions). The graph pauses
with `interrupt()` before anything is approved; it resumes with the reviewer's decisions:
    Command(resume={"approved": [...variant_ids], "rejected": [...], "reviewer": "TS"})
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, interrupt

from src.agent.state import AgentState, AgentTools, event

RETRY = RetryPolicy(max_attempts=2, initial_interval=2.0)


def build_graph(tools: AgentTools, checkpointer: Any = None):
    def discover(state: AgentState) -> dict:
        if state.get("run_ids"):
            return {"log": [event("discover", "using existing runs", run_ids=state["run_ids"])]}
        run_ids = tools.discover(
            state.get("panel_version", "v0"), state.get("providers"),
            state.get("repeats", 1), state.get("limit"),
        )  # fmt: skip
        return {
            "run_ids": run_ids,
            "log": [event("discover", "discovery runs done", run_ids=run_ids)],
        }

    def diagnose(state: AgentState) -> dict:
        logs, errors = [], []
        for run_id in state["run_ids"]:
            try:
                out = tools.diagnose(
                    run_id, state.get("label_sentiment", False), state.get("check_accuracy", False)
                )
                logs.append(event("diagnose", "diagnosed", run_id=run_id, **out))
            except Exception as exc:  # keep going with the other runs
                errors.append(f"diagnose {run_id}: {exc}")
        return {"log": logs, "errors": errors}

    def opportunities(state: AgentState) -> dict:
        found: list[tuple[str, float]] = []
        errors = []
        for run_id in state["run_ids"]:
            try:
                found += tools.find_opportunities(run_id)
            except Exception as exc:
                errors.append(f"opportunities {run_id}: {exc}")
        ranked = [oid for oid, _ in sorted(found, key=lambda x: x[1], reverse=True)]
        return {
            "opportunity_ids": ranked,
            "log": [event("opportunities", f"{len(ranked)} opportunities")],
            "errors": errors,
        }

    def route_after_opportunities(state: AgentState) -> str:
        return "draft" if state.get("opportunity_ids") else "report"

    def draft(state: AgentState) -> dict:
        drafts, errors = [], []
        for oid in state["opportunity_ids"][: state.get("max_drafts", 3)]:
            try:
                drafts.append(tools.draft(oid))
            except Exception as exc:  # e.g. empty knowledge base: log, do not crash the run
                errors.append(f"draft {oid}: {exc}")
        return {"drafts": drafts, "errors": errors,
                "log": [event("draft", f"{len(drafts)} drafts created")]}  # fmt: skip

    def route_after_draft(state: AgentState) -> str:
        return "human_review" if state.get("drafts") else "report"

    def human_review(state: AgentState) -> dict:
        decision = interrupt(
            {
                "message": "Review the drafts, then resume with approved / rejected variant ids.",
                "drafts": state["drafts"],
            }  # fmt: skip
        )
        known = {d["variant_id"] for d in state["drafts"]}
        approved = [v for v in decision.get("approved", []) if v in known]
        rejected = [v for v in decision.get("rejected", []) if v in known]
        reviewer = decision.get("reviewer", "unknown")
        for v in approved:
            tools.review(v, "approved", reviewer, decision.get("notes", ""))
        for v in rejected:
            tools.review(v, "rejected", reviewer, decision.get("notes", ""))
        return {
            "approved_variant_ids": approved,
            "rejected_variant_ids": rejected,
            "log": [event("human_review", f"{len(approved)} approved, {len(rejected)} rejected",
                          reviewer=reviewer)],
        }  # fmt: skip

    def plan_experiments(state: AgentState) -> dict:
        by_variant = {d["variant_id"]: d for d in state["drafts"]}
        baseline = state["run_ids"][0]
        exp_ids, errors = [], []
        for v in state.get("approved_variant_ids", []):
            try:
                exp_ids.append(tools.plan_experiment(
                    v, by_variant[v]["opportunity_id"], baseline, "agent"))  # fmt: skip
            except Exception as exc:
                errors.append(f"experiment {v}: {exc}")
        return {"experiment_ids": exp_ids, "errors": errors,
                "log": [event("plan_experiments", f"{len(exp_ids)} planned")]}  # fmt: skip

    def report(state: AgentState) -> dict:
        summary = {
            "runs": len(state.get("run_ids", [])),
            "opportunities": len(state.get("opportunity_ids", [])),
            "drafts": len(state.get("drafts", [])),
            "approved": len(state.get("approved_variant_ids", [])),
            "experiments_planned": len(state.get("experiment_ids", [])),
            "errors": len(state.get("errors", [])),
        }
        return {"report": summary, "log": [event("report", "done", **summary)]}

    g = StateGraph(AgentState)
    for name, fn in [("discover", discover), ("diagnose", diagnose),
                     ("opportunities", opportunities), ("draft", draft),
                     ("human_review", human_review), ("plan_experiments", plan_experiments),
                     ("report", report)]:  # fmt: skip
        retry = RETRY if name in {"discover", "diagnose", "opportunities"} else None
        g.add_node(name, fn, retry_policy=retry)
    g.add_edge(START, "discover")
    g.add_edge("discover", "diagnose")
    g.add_edge("diagnose", "opportunities")
    g.add_conditional_edges("opportunities", route_after_opportunities, ["draft", "report"])
    g.add_conditional_edges("draft", route_after_draft, ["human_review", "report"])
    g.add_edge("human_review", "plan_experiments")
    g.add_edge("plan_experiments", "report")
    g.add_edge("report", END)
    return g.compile(checkpointer=checkpointer)
