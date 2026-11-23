import pytest

from src.experimentation import (
    CreateExperimentInput,
    RetestInput,
    compare_experiment,
    create_experiment,
    run_retest,
)
from src.experimentation.analysis import compare, interpret
from src.experimentation.models import BaselineRun, Counts


class FakeRepo:
    def __init__(self) -> None:
        self.exps: dict[str, dict] = {}
        self.results: dict[str, list] = {}
        self.counts_by_run = {
            "base": {1: Counts(x=3, n=30), 2: Counts(x=27, n=30)},
            "retest": {1: Counts(x=18, n=30), 2: Counts(x=26, n=30)},
        }

    def load_run(self, run_id):
        if run_id not in {"base", "retest"}:
            raise ValueError("Run not found")
        return BaselineRun(run_id=run_id, panel_version="v0", provider="perplexity")

    def opportunity_prompt_ids(self, opportunity_id):
        return ["SUN-001", "SUN-002"] if opportunity_id == "opp1" else []

    def run_prompt_ids(self, run_id):
        return ["ALL-1", "ALL-2", "ALL-3"]

    def create(self, inp, prompt_ids, hypothesis):
        eid = f"e{len(self.exps) + 1}"
        self.exps[eid] = {"experiment_id": eid, "baseline_run_id": inp.baseline_run_id,
                          "retest_run_id": None, "prompt_ids": prompt_ids, "status": "planned",
                          "design": inp.design, "hypothesis": hypothesis}  # fmt: skip
        return eid

    def load(self, eid):
        return self.exps[eid]

    def set_retest(self, eid, run_id):
        self.exps[eid].update(retest_run_id=run_id, status="running")

    def counts(self, run_id, prompt_ids):
        return self.counts_by_run[run_id]

    def save_results(self, eid, rows):
        self.results[eid] = rows
        self.exps[eid]["status"] = "done"


def test_create_uses_opportunity_prompts_then_falls_back() -> None:
    repo = FakeRepo()
    e1 = create_experiment(CreateExperimentInput(baseline_run_id="base", variant_id="v1",
                                                 opportunity_id="opp1"), repo)  # fmt: skip
    assert repo.exps[e1]["prompt_ids"] == ["SUN-001", "SUN-002"]
    assert "increases" in repo.exps[e1]["hypothesis"]
    e2 = create_experiment(CreateExperimentInput(baseline_run_id="base",
                                                 design="repeat_baseline"), repo)  # fmt: skip
    assert repo.exps[e2]["prompt_ids"] == ["ALL-1", "ALL-2", "ALL-3"]
    assert "noise" in repo.exps[e2]["hypothesis"]


def test_create_validations() -> None:
    with pytest.raises(ValueError, match="variant_id"):
        create_experiment(CreateExperimentInput(baseline_run_id="base"), FakeRepo())
    with pytest.raises(ValueError, match="not found"):
        create_experiment(CreateExperimentInput(baseline_run_id="nope", variant_id="v"), FakeRepo())


def test_retest_flow_and_results() -> None:
    repo = FakeRepo()
    eid = create_experiment(CreateExperimentInput(baseline_run_id="base", variant_id="v1",
                                                  opportunity_id="opp1"), repo)  # fmt: skip
    calls = {}

    def discover(panel, provider, prompt_ids, repeats):
        calls["discover"] = (panel, provider, prompt_ids, repeats)
        return "retest"

    def diagnose(run_id):
        calls["diagnose"] = run_id

    out = run_retest(RetestInput(experiment_id=eid, repeats=3), repo, discover, diagnose)
    assert calls["discover"] == ("v0", "perplexity", ["SUN-001", "SUN-002"], 3)
    assert calls["diagnose"] == "retest" and out.status == "done"
    target = next(r for r in out.results if r.brand_id == 1)
    assert target.baseline_value == 0.1 and target.retest_value == 0.6 and target.delta == 0.5
    assert target.ci_low > 0 and target.p_value < 0.001 and "higher" in target.interpretation
    competitor = next(r for r in out.results if r.brand_id == 2)
    assert "No detectable change" in competitor.interpretation
    assert all("Observational" in r.interpretation for r in out.results)
    with pytest.raises(ValueError, match="already completed"):
        run_retest(RetestInput(experiment_id=eid), repo, discover, diagnose)


def test_compare_needs_retest() -> None:
    repo = FakeRepo()
    eid = create_experiment(CreateExperimentInput(baseline_run_id="base", variant_id="v"), repo)
    with pytest.raises(ValueError, match="no re-test"):
        compare_experiment(eid, repo)


def test_compare_handles_missing_brand_and_no_data() -> None:
    rows = compare("e", {1: Counts(x=1, n=10)}, {})
    assert rows[0].retest_value is None and rows[0].interpretation == "Not enough data to compare."
    assert interpret(None, None, 0, 0) == "Not enough data to compare."
