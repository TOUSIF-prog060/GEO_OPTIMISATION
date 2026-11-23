import pytest

from src.agent import memory_checkpointer, resume_run, start_run
from src.agent.graph import build_graph


class FakeTools:
    def __init__(self, n_opps: int = 3, draft_fails: set[str] | None = None) -> None:
        self.calls: list[tuple] = []
        self.records: list[tuple] = []
        self.n_opps = n_opps
        self.draft_fails = draft_fails or set()
        self.discover_attempts = 0

    def discover(self, panel_version, providers, repeats, limit):
        self.calls.append(("discover", panel_version, repeats, limit))
        return ["run-A", "run-B"]

    def diagnose(self, run_id, label_sentiment, check_accuracy):
        self.calls.append(("diagnose", run_id))
        return {"n_responses": 10}

    def find_opportunities(self, run_id):
        self.calls.append(("opportunities", run_id))
        base = 50 if run_id == "run-A" else 10
        return [(f"{run_id}-o{i}", base - i) for i in range(self.n_opps)]

    def draft(self, opportunity_id):
        self.calls.append(("draft", opportunity_id))
        if opportunity_id in self.draft_fails:
            raise ValueError("Knowledge base is empty")
        return {"variant_id": f"v-{opportunity_id}", "opportunity_id": opportunity_id,
                "title": "t", "grounded": True}  # fmt: skip

    def review(self, variant_id, status, reviewer, notes):
        self.calls.append(("review", variant_id, status, reviewer))

    def plan_experiment(self, variant_id, opportunity_id, baseline_run_id, created_by):
        self.calls.append(("experiment", variant_id, baseline_run_id))
        return f"exp-{variant_id}"

    def record(self, thread_id, status, last_node, summary):
        self.records.append((thread_id, status, last_node))


PARAMS = {"panel_version": "v0", "repeats": 1, "limit": 5, "max_drafts": 2}


def test_runs_until_human_review_then_resumes() -> None:
    tools, cp = FakeTools(), memory_checkpointer()
    tid, status, pending, state = start_run(tools, cp, PARAMS, thread_id="t1")

    assert status == "awaiting_review"
    drafts = pending[0]["drafts"]
    # top-2 opportunities by priority across both runs, all from run-A
    assert [d["opportunity_id"] for d in drafts] == ["run-A-o0", "run-A-o1"]
    assert not any(c[0] in {"review", "experiment"} for c in tools.calls)  # nothing approved yet
    assert tools.records[-1] == ("t1", "awaiting_review", "human_review")

    status, pending, state = resume_run(
        tools, cp, "t1",
        {"approved": ["v-run-A-o0", "v-unknown"], "rejected": ["v-run-A-o1"], "reviewer": "TS"},
    )  # fmt: skip
    assert status == "completed" and not pending
    assert ("review", "v-run-A-o0", "approved", "TS") in tools.calls
    assert ("review", "v-run-A-o1", "rejected", "TS") in tools.calls
    assert ("experiment", "v-run-A-o0", "run-A") in tools.calls  # baseline = first run
    assert not any(c[1] == "v-unknown" for c in tools.calls if c[0] == "review")  # ignored
    assert state["report"] == {"runs": 2, "opportunities": 6, "drafts": 2, "approved": 1,
                               "experiments_planned": 1, "errors": 0}  # fmt: skip
    assert [e["node"] for e in state["log"]][-1] == "report"


def test_existing_runs_skip_discovery() -> None:
    tools = FakeTools()
    start_run(tools, memory_checkpointer(), {**PARAMS, "run_ids": ["run-X"]}, "t2")
    assert not any(c[0] == "discover" for c in tools.calls)
    assert ("diagnose", "run-X") in tools.calls


def test_no_opportunities_goes_straight_to_report() -> None:
    tools = FakeTools(n_opps=0)
    _, status, pending, state = start_run(tools, memory_checkpointer(), PARAMS, "t3")
    assert status == "completed" and state["report"]["opportunities"] == 0
    assert not any(c[0] == "draft" for c in tools.calls)


def test_draft_failures_are_logged_not_fatal() -> None:
    tools = FakeTools(draft_fails={"run-A-o0", "run-A-o1"})
    _, status, _, state = start_run(tools, memory_checkpointer(), PARAMS, "t4")
    assert status == "completed"  # no drafts -> skips review
    assert len(state["errors"]) == 2 and "Knowledge base is empty" in state["errors"][0]


def test_graph_shape() -> None:
    graph = build_graph(FakeTools())
    nodes = set(graph.get_graph().nodes)
    assert {"discover", "diagnose", "opportunities", "draft", "human_review",
            "plan_experiments", "report"} <= nodes  # fmt: skip


def test_failure_is_recorded() -> None:
    class Broken(FakeTools):
        def discover(self, *a):
            raise RuntimeError("API down")

    tools = Broken()
    with pytest.raises(RuntimeError):
        start_run(tools, memory_checkpointer(), PARAMS, "t5")
    assert tools.records[-1][1] == "failed"
