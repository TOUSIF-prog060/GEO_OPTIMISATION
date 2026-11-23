"""Experimentation lab entry points.

create_experiment()  plan: baseline run + prompt subset (+ approved content variant)
run_retest()         re-ask the same prompts on the same provider (discovery, run_type=retest),
                     diagnose the new run, then compare()
compare_experiment() baseline vs re-test mention rates with CI and p-value (observational)

Designs
  content_variant  re-test after an approved variant is published (on the real site or a
                   clearly labelled demo page if real-brand content cannot be changed)
  repeat_baseline  re-test with NO change: measures natural run-to-run noise, the reference
                   to compare content-variant results against
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from src.experimentation.analysis import compare
from src.experimentation.models import (
    CreateExperimentInput,
    ExperimentOutput,
    RetestInput,
)
from src.experimentation.repository import ExperimentRepository

logger = logging.getLogger(__name__)

# (panel_version, provider, prompt_ids, repeats) -> retest run_id
DiscoverFn = Callable[[str, str, list[str], int], str]
DiagnoseFn = Callable[[str], None]


def create_experiment(inp: CreateExperimentInput, repo: ExperimentRepository) -> str:
    repo.load_run(inp.baseline_run_id)  # must exist
    if inp.design == "content_variant" and not inp.variant_id:
        raise ValueError("A content_variant experiment needs an approved variant_id.")
    prompt_ids = inp.prompt_ids
    if not prompt_ids and inp.opportunity_id:
        prompt_ids = repo.opportunity_prompt_ids(inp.opportunity_id)
    if not prompt_ids:
        prompt_ids = repo.run_prompt_ids(inp.baseline_run_id)
    if not prompt_ids:
        raise ValueError("No prompts to re-test.")
    hypothesis = inp.hypothesis or (
        "Publishing the approved content increases the target brand's mention rate on these "
        "prompts." if inp.design == "content_variant"
        else "With no change, mention rates stay within run-to-run noise."
    )  # fmt: skip
    exp_id = repo.create(inp, prompt_ids, hypothesis)
    logger.info("Experiment %s planned on %d prompts", exp_id, len(prompt_ids))
    return exp_id


def compare_experiment(experiment_id: str, repo: ExperimentRepository) -> ExperimentOutput:
    exp = repo.load(experiment_id)
    if not exp["retest_run_id"]:
        raise ValueError("This experiment has no re-test run yet.")
    rows = compare(
        experiment_id,
        repo.counts(exp["baseline_run_id"], exp["prompt_ids"]),
        repo.counts(exp["retest_run_id"], exp["prompt_ids"]),
    )
    repo.save_results(experiment_id, rows)
    return ExperimentOutput(
        experiment_id=experiment_id, status="done", retest_run_id=exp["retest_run_id"], results=rows
    )


def run_retest(
    inp: RetestInput,
    repo: ExperimentRepository,
    discover_fn: DiscoverFn,
    diagnose_fn: DiagnoseFn,
) -> ExperimentOutput:
    """Billed: re-asks the experiment prompts. discover_fn/diagnose_fn wrap the engines."""
    exp = repo.load(inp.experiment_id)
    if exp["status"] == "done":
        raise ValueError("Experiment already completed. Plan a new one to re-test again.")
    base = repo.load_run(exp["baseline_run_id"])
    retest_run_id = discover_fn(base.panel_version, base.provider, exp["prompt_ids"], inp.repeats)
    repo.set_retest(inp.experiment_id, retest_run_id)
    diagnose_fn(retest_run_id)
    return compare_experiment(inp.experiment_id, repo)
