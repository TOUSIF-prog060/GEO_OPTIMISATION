"""Agent evaluation: run the real LangGraph workflow against scripted tools in a sandbox
(in-memory checkpoints, no database, no API calls) and check its behaviour scenario by scenario.

Parameters measured: task completion, correct step order, human-review gate respected,
approvals applied exactly as given, failure recovery, max-drafts limit, and step latency.
"""

from __future__ import annotations

import time
from typing import Any

from src.agent import memory_checkpointer, resume_run, start_run

FULL_PATH = ["discover", "diagnose", "opportunities", "draft", "human_review",
             "plan_experiments", "report"]  # fmt: skip


class ScriptedTools:
    """AgentTools with configurable behaviour and fault injection."""

    def __init__(self, n_opps: int = 3, fail_discover_times: int = 0,
                 fail_drafts: set[str] | None = None, diagnose_fails: set[str] | None = None,
                 always_fail_discover: bool = False) -> None:  # fmt: skip
        self.calls: list[tuple] = []
        self.records: list[tuple] = []
        self.n_opps = n_opps
        self.fail_discover_times = fail_discover_times
        self.always_fail_discover = always_fail_discover
        self.fail_drafts = fail_drafts or set()
        self.diagnose_fails = diagnose_fails or set()

    def discover(self, panel_version, providers, repeats, limit):
        self.calls.append(("discover",))
        if self.always_fail_discover or self.fail_discover_times > 0:
            self.fail_discover_times -= 1
            raise ConnectionError("provider timeout (injected)")
        return ["run-A", "run-B"]

    def diagnose(self, run_id, label_sentiment, check_accuracy):
        self.calls.append(("diagnose", run_id))
        if run_id in self.diagnose_fails:
            raise RuntimeError("diagnose failed (injected)")
        return {"n_responses": 10}

    def find_opportunities(self, run_id):
        self.calls.append(("opportunities", run_id))
        base = 50 if run_id == "run-A" else 10
        return [(f"{run_id}-o{i}", base - i) for i in range(self.n_opps)]

    def draft(self, opportunity_id):
        self.calls.append(("draft", opportunity_id))
        if opportunity_id in self.fail_drafts:
            raise ValueError("knowledge base empty (injected)")
        return {"variant_id": f"v-{opportunity_id}", "opportunity_id": opportunity_id,
                "title": f"Draft for {opportunity_id}", "grounded": True}  # fmt: skip

    def review(self, variant_id, status, reviewer, notes):
        self.calls.append(("review", variant_id, status))

    def plan_experiment(self, variant_id, opportunity_id, baseline_run_id, created_by):
        self.calls.append(("experiment", variant_id))
        return f"exp-{variant_id}"

    def record(self, thread_id, status, last_node, summary):
        self.records.append((thread_id, status, last_node))


PARAMS = {"panel_version": "v0", "repeats": 1, "limit": 5, "max_drafts": 2}


def _nodes(state: dict) -> list[str]:
    seen: list[str] = []
    for e in state.get("log", []):
        if not seen or seen[-1] != e["node"]:
            seen.append(e["node"])
    return seen


def _run(name: str, tools: ScriptedTools, params: dict, decision: dict | None,
         checks) -> dict[str, Any]:  # fmt: skip
    cp = memory_checkpointer()
    t0 = time.perf_counter()
    try:
        tid, status, pending, state = start_run(tools, cp, params, thread_id=name)
        before_review = list(tools.calls)
        if status == "awaiting_review" and decision is not None:
            status, pending, state = resume_run(tools, cp, tid, decision)
        result = {"status": status, "state": state, "before_review": before_review,
                  "error": None}  # fmt: skip
    except Exception as exc:
        result = {"status": "raised", "state": {}, "before_review": list(tools.calls),
                  "error": f"{type(exc).__name__}: {exc}"}  # fmt: skip
    result["seconds"] = time.perf_counter() - t0
    problems = [msg for ok, msg in checks(result, tools) if not ok]
    return {"scenario": name, "passed": not problems, "problems": problems,
            "status": result["status"], "path": _nodes(result["state"]),
            "seconds": round(result["seconds"], 3)}  # fmt: skip


def scenarios() -> list[dict[str, Any]]:
    out = []

    # 1. Happy path: full loop, pauses, approve one, reject one.
    t = ScriptedTools()
    out.append(_run("happy_path", t, PARAMS,
                    {"approved": ["v-run-A-o0"], "rejected": ["v-run-A-o1"], "reviewer": "QA"},
                    lambda r, t: [
                        (r["status"] == "completed", f"status {r['status']}"),
                        (_nodes(r["state"]) == FULL_PATH, f"path {_nodes(r['state'])}"),
                        (("review", "v-run-A-o0", "approved") in t.calls, "approval not applied"),
                        (("review", "v-run-A-o1", "rejected") in t.calls, "rejection not applied"),
                        (("experiment", "v-run-A-o0") in t.calls, "no experiment for approval"),
                        (not any(c[0] == "experiment" and c[1] == "v-run-A-o1" for c in t.calls),
                         "experiment planned for a rejected draft"),
                    ]))  # fmt: skip

    # 2. Human gate: nothing is approved or planned before the reviewer resumes.
    t = ScriptedTools()
    out.append(_run("human_gate", t, PARAMS, None, lambda r, t: [
        (r["status"] == "awaiting_review", f"status {r['status']}"),
        (not any(c[0] in {"review", "experiment"} for c in t.calls),
         "acted before human review"),
        (t.records[-1][1] == "awaiting_review", "run status not recorded as awaiting_review"),
    ]))  # fmt: skip

    # 3. Reviewer rejects everything: no experiments.
    t = ScriptedTools()
    out.append(_run("reject_all", t, PARAMS,
                    {"approved": [], "rejected": ["v-run-A-o0", "v-run-A-o1"], "reviewer": "QA"},
                    lambda r, t: [
                        (r["status"] == "completed", f"status {r['status']}"),
                        (not any(c[0] == "experiment" for c in t.calls), "experiment planned"),
                        (r["state"].get("report", {}).get("approved") == 0, "approved count"),
                    ]))  # fmt: skip

    # 4. Forged approval: ids that the agent never drafted must be ignored.
    t = ScriptedTools()
    out.append(_run("forged_approval", t, PARAMS,
                    {"approved": ["v-not-drafted"], "reviewer": "QA"},
                    lambda r, t: [
                        (not any(c[0] == "review" and c[1] == "v-not-drafted" for c in t.calls),
                         "unknown variant was approved"),
                    ]))  # fmt: skip

    # 5. One draft fails: the run continues and logs the error.
    t = ScriptedTools(fail_drafts={"run-A-o0"})
    out.append(_run("draft_failure_recovery", t, PARAMS,
                    {"approved": ["v-run-A-o1"], "reviewer": "QA"},
                    lambda r, t: [
                        (r["status"] == "completed", f"status {r['status']}"),
                        (any("draft run-A-o0" in e for e in r["state"].get("errors", [])),
                         "draft error not logged"),
                        (r["state"].get("report", {}).get("drafts") == 1, "drafts count"),
                    ]))  # fmt: skip

    # 6. Transient discovery failure: retried, then succeeds.
    t = ScriptedTools(fail_discover_times=1)
    out.append(_run("transient_failure_retry", t, PARAMS,
                    {"approved": [], "reviewer": "QA"},
                    lambda r, t: [
                        (r["status"] == "completed", f"status {r['status']} {r['error']}"),
                        (sum(c[0] == "discover" for c in t.calls) == 2, "not retried once"),
                    ]))  # fmt: skip

    # 7. Persistent discovery failure: fails cleanly and records it, no partial actions.
    t = ScriptedTools(always_fail_discover=True)
    out.append(_run("persistent_failure", t, PARAMS, None, lambda r, t: [
        (r["status"] == "raised", f"status {r['status']}"),
        (any(rec[1] == "failed" for rec in t.records), "failure not recorded"),
        (not any(c[0] in {"draft", "review", "experiment"} for c in t.calls),
         "acted after a failed discovery"),
    ]))  # fmt: skip

    # 8. One run fails to diagnose: the other run still produces opportunities.
    t = ScriptedTools(diagnose_fails={"run-B"})
    out.append(_run("partial_diagnose_failure", t, PARAMS,
                    {"approved": [], "reviewer": "QA"},
                    lambda r, t: [
                        (r["status"] == "completed", f"status {r['status']}"),
                        (any("diagnose run-B" in e for e in r["state"].get("errors", [])),
                         "diagnose error not logged"),
                    ]))  # fmt: skip

    # 9. No opportunities: skips drafting and review, still reports.
    t = ScriptedTools(n_opps=0)
    out.append(_run("no_opportunities", t, PARAMS, None, lambda r, t: [
        (r["status"] == "completed", f"status {r['status']}"),
        (_nodes(r["state"]) == ["discover", "diagnose", "opportunities", "report"],
         f"path {_nodes(r['state'])}"),
    ]))  # fmt: skip

    # 10. Reuse existing runs: no discovery calls (no cost).
    t = ScriptedTools()
    out.append(_run("reuse_runs_no_cost", t, {**PARAMS, "run_ids": ["run-X"]}, None,
                    lambda r, t: [
                        (not any(c[0] == "discover" for c in t.calls), "discovery was called"),
                        (("diagnose", "run-X") in t.calls, "given run not diagnosed"),
                    ]))  # fmt: skip

    # 11. max_drafts is a hard limit and picks the highest-priority gaps.
    t = ScriptedTools(n_opps=5)
    out.append(_run("max_drafts_priority", t, {**PARAMS, "max_drafts": 3}, None, lambda r, t: [
        (sum(c[0] == "draft" for c in t.calls) == 3, "draft count"),
        ([c[1] for c in t.calls if c[0] == "draft"] == ["run-A-o0", "run-A-o1", "run-A-o2"],
         "not the top-priority gaps"),
    ]))  # fmt: skip
    return out


def eval_agent() -> dict[str, Any]:
    results = scenarios()
    passed = [r for r in results if r["passed"]]
    return {
        "metrics": {
            "scenarios": len(results),
            "passed": len(passed),
            "pass_rate": len(passed) / len(results),
            "mean_seconds": round(sum(r["seconds"] for r in results) / len(results), 3),
        },
        "scenarios": results,
        "failures": [r for r in results if not r["passed"]],
    }
