"""Baseline vs re-test comparison (pure functions).

For each brand on the experiment's prompt subset:
  baseline_value / retest_value = mention rate among successful responses
  delta = retest - baseline, 95% Wald CI, two-sided two-proportion z-test p-value
Interpretation is deliberately cautious: AI answers vary between runs, providers update
models, and other sites change too, so a difference is an OBSERVATION, not proof that the
content change caused it.
"""

from __future__ import annotations

from src.common.stats import diff_ci, two_proportion_z
from src.experimentation.models import Counts, ResultRow

OBSERVATIONAL = "Observational: other factors (model updates, other sites) may contribute."


def interpret(delta: float | None, ci: tuple[float, float] | None, n_b: int, n_r: int) -> str:
    if n_b == 0 or n_r == 0 or delta is None or ci is None:
        return "Not enough data to compare."
    if ci[0] <= 0 <= ci[1]:
        return f"No detectable change (95% CI {ci[0]:+.0%} to {ci[1]:+.0%}). {OBSERVATIONAL}"
    direction = "higher" if delta > 0 else "lower"
    return (
        f"Mention rate {abs(delta):.0%} {direction} after the change "
        f"(95% CI {ci[0]:+.0%} to {ci[1]:+.0%}). {OBSERVATIONAL}"
    )


def compare(
    experiment_id: str, baseline: dict[int, Counts], retest: dict[int, Counts]
) -> list[ResultRow]:
    rows: list[ResultRow] = []
    for brand_id in sorted(set(baseline) | set(retest)):
        b = baseline.get(brand_id, Counts(x=0, n=0))
        r = retest.get(brand_id, Counts(x=0, n=0))
        bv = b.x / b.n if b.n else None
        rv = r.x / r.n if r.n else None
        delta = rv - bv if bv is not None and rv is not None else None
        ci = diff_ci(r.x, r.n, b.x, b.n)
        _, p = two_proportion_z(r.x, r.n, b.x, b.n)
        rows.append(
            ResultRow(
                experiment_id=experiment_id,
                brand_id=brand_id,
                baseline_value=None if bv is None else round(bv, 4),
                retest_value=None if rv is None else round(rv, 4),
                delta=None if delta is None else round(delta, 4),
                ci_low=None if ci is None else round(ci[0], 4),
                ci_high=None if ci is None else round(ci[1], 4),
                p_value=None if p is None else round(p, 4),
                n_baseline=b.n,
                n_retest=r.n,
                interpretation=interpret(delta, ci, b.n, r.n),
            )
        )
    return rows
