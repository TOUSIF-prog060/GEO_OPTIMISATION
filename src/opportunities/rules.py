"""Opportunity rules v1: turn diagnostic evidence into scored, evidence-linked gaps.

Every opportunity carries:
  severity    0-1, size of the gap
  confidence  0-1; for two-proportion gaps = 1 - one-sided p-value (z-test); otherwise the
              documented sample-size heuristic n / (n + 10)
  effort      low / medium / high (by gap type, configurable)
  priority    100 * severity * confidence / effort weight
  evidence    response_ids that show the gap
Opportunities are observations on the prompt sample, not proof of a market-wide problem.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from src.common.stats import one_sided_p, sample_size_confidence
from src.diagnostics.parsing import classify_domain
from src.opportunities.models import (
    GoldVisibility,
    Opportunity,
    OpportunityInputs,
    OpportunityRules,
)

EFFORT_WEIGHT = {"low": 1, "medium": 2, "high": 3}
ALL = "ALL"


def priority(severity: float, confidence: float, effort: str) -> float:
    return round(100 * severity * confidence / EFFORT_WEIGHT[effort], 2)


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


class _Ctx:
    """Indexes built once per run."""

    def __init__(self, inp: OpportunityInputs) -> None:
        self.inp = inp
        self.target = inp.target
        self.names = {b.brand_id: b.name for b in inp.brands}
        self.ok = [r for r in inp.responses if r.ok]
        self.cat_of = {r.response_id: r.category for r in self.ok}
        self.mentioned = {(m.response_id, m.brand_id) for m in inp.mentions if m.mentioned}
        self.rank = {
            (m.response_id, m.brand_id): m.rank_in_list for m in inp.mentions if m.rank_in_list
        }
        self.vis: dict[tuple[str, int], GoldVisibility] = {
            (v.category, v.brand_id): v for v in inp.visibility
        }

    def ids_in(self, category: str) -> list[str]:
        return [r.response_id for r in self.ok if category == ALL or r.category == category]

    def categories(self) -> list[str]:
        return sorted({v.category for v in self.inp.visibility if v.category != ALL})

    def competitors(self) -> list[int]:
        return [b.brand_id for b in self.inp.brands if not b.is_target]


def _make(
    ctx: _Ctx,
    rules: OpportunityRules,
    gap_type: str,
    category: str | None,
    title: str,
    rationale: str,
    validation: str,
    severity: float,
    confidence: float,
    evidence: Iterable[str],
    metric: str | None = None,
    target_value: float | None = None,
    bench_value: float | None = None,
    bench_brand: int | None = None,
) -> Opportunity:
    effort = rules.effort[gap_type]
    severity = round(max(0.0, min(1.0, severity)), 4)
    confidence = round(max(0.0, min(1.0, confidence)), 3)
    return Opportunity(
        run_id=ctx.inp.run_id,
        brand_id=ctx.target.brand_id,
        gap_type=gap_type,
        category=category,
        title=title,
        rationale=rationale,
        validation_approach=validation,
        metric_name=metric,
        target_value=target_value,
        benchmark_value=bench_value,
        benchmark_brand_id=bench_brand,
        severity=severity,
        confidence=confidence,
        effort=effort,
        priority_score=priority(severity, confidence, effort),
        evidence_response_ids=sorted(set(evidence))[: rules.max_evidence],
        dedupe_key=f"{gap_type}|{category or ALL}",
        rule_version=rules.rule_version,
    )


def _best_competitor(ctx: _Ctx, category: str, field: str, highest: bool = True):
    rows = [
        ctx.vis[(category, b)]
        for b in ctx.competitors()
        if (category, b) in ctx.vis and getattr(ctx.vis[(category, b)], field) is not None
    ]
    if not rows:
        return None
    return (max if highest else min)(rows, key=lambda v: getattr(v, field))


def _retest(category: str | None, n: int) -> str:
    where = f"the {n} '{category}' prompts" if category else f"the {n} affected prompts"
    return (
        f"After the change, re-run {where} with 3 repeats on the same providers and compare "
        "against this run in the Experimentation Lab. Treat the result as observational."
    )


# ---------------------------------------------------------------- rules


def visibility_gaps(ctx: _Ctx, rules: OpportunityRules) -> list[Opportunity]:
    out = []
    t = ctx.target.brand_id
    for cat in ctx.categories():
        tv = ctx.vis.get((cat, t))
        best = _best_competitor(ctx, cat, "mention_rate")
        if not tv or not best or tv.n_responses < rules.min_responses or tv.mention_rate is None:
            continue
        gap = best.mention_rate - tv.mention_rate
        if gap < rules.mention_gap:
            continue
        n = tv.n_responses
        p = one_sided_p(round(best.mention_rate * n), n, round(tv.mention_rate * n), n)
        ids = ctx.ids_in(cat)
        evidence = [
            r for r in ids if (r, best.brand_id) in ctx.mentioned and (r, t) not in ctx.mentioned
        ]
        comp = ctx.names[best.brand_id]
        out.append(
            _make(
                ctx,
                rules,
                "visibility_gap",
                cat,
                f"{ctx.target.name} is missing from '{cat}' answers "
                f"({_pct(tv.mention_rate)} vs {comp} {_pct(best.mention_rate)})",
                f"In {n} '{cat}' answers, {comp} was mentioned in {_pct(best.mention_rate)} and "
                f"{ctx.target.name} in {_pct(tv.mention_rate)}. {len(evidence)} answers name "
                f"{comp} but not {ctx.target.name}.",
                _retest(cat, len(ids)),
                gap,
                1 - (p if p is not None else 1.0),
                evidence,
                "mention_rate",
                tv.mention_rate,
                best.mention_rate,
                best.brand_id,
            )  # fmt: skip
        )
    return out


def ranking_gaps(ctx: _Ctx, rules: OpportunityRules) -> list[Opportunity]:
    out = []
    t = ctx.target.brand_id
    for cat in ctx.categories():
        tv = ctx.vis.get((cat, t))
        best = _best_competitor(ctx, cat, "avg_rank", highest=False)
        if not tv or not best or tv.avg_rank is None or tv.n_responses < rules.min_responses:
            continue
        diff = tv.avg_rank - best.avg_rank
        if diff < rules.rank_gap:
            continue
        ids = ctx.ids_in(cat)
        evidence = [
            r for r in ids
            if (r, t) in ctx.rank and (r, best.brand_id) in ctx.rank
            and ctx.rank[(r, t)] > ctx.rank[(r, best.brand_id)]
        ]  # fmt: skip
        comp = ctx.names[best.brand_id]
        out.append(
            _make(
                ctx,
                rules,
                "ranking_gap",
                cat,
                f"{ctx.target.name} ranks lower than {comp} in '{cat}' lists "
                f"(avg #{tv.avg_rank:.1f} vs #{best.avg_rank:.1f})",
                f"When both appear in ranked lists for '{cat}', {ctx.target.name} is placed "
                f"below {comp} in {len(evidence)} answers.",
                _retest(cat, len(ids)),
                diff / 5,
                sample_size_confidence(len(evidence)),
                evidence,
                "avg_rank",
                tv.avg_rank,
                best.avg_rank,
                best.brand_id,
            )  # fmt: skip
        )
    return out


def citation_gaps(ctx: _Ctx, rules: OpportunityRules) -> list[Opportunity]:
    out = []
    t = ctx.target.brand_id
    owner: dict[str, set[int]] = defaultdict(set)  # response_id -> brand_ids whose site is cited
    n_cites: dict[str, int] = defaultdict(int)
    for c in ctx.inp.citations:
        n_cites[ctx.cat_of.get(c.response_id, "")] += 1
        ref = classify_domain(c.domain, ctx.inp.domains)
        if ref and ref.brand_id is not None:
            owner[c.response_id].add(ref.brand_id)
    for cat in ctx.categories():
        tv = ctx.vis.get((cat, t))
        best = _best_competitor(ctx, cat, "citation_share")
        if not tv or not best or tv.citation_share is None or tv.n_responses < rules.min_responses:
            continue
        gap = best.citation_share - tv.citation_share
        if gap < rules.citation_gap:
            continue
        n = n_cites.get(cat, 0)
        p = one_sided_p(round(best.citation_share * n), n, round(tv.citation_share * n), n)
        evidence = [r for r in ctx.ids_in(cat) if best.brand_id in owner[r] and t not in owner[r]]
        comp = ctx.names[best.brand_id]
        out.append(
            _make(
                ctx,
                rules,
                "citation_gap",
                cat,
                f"{comp}'s own site is cited more than {ctx.target.name}'s in '{cat}' "
                f"({_pct(best.citation_share)} vs {_pct(tv.citation_share)} of citations)",
                f"Out of {n} citations in '{cat}' answers, {comp}-owned pages make up "
                f"{_pct(best.citation_share)}; {ctx.target.name}-owned pages "
                f"{_pct(tv.citation_share)}. {len(evidence)} answers cite {comp} but not "
                f"{ctx.target.name}.",
                _retest(cat, len(ctx.ids_in(cat))),
                gap,
                1 - (p if p is not None else 1.0),
                evidence,
                "citation_share",
                tv.citation_share,
                best.citation_share,
                best.brand_id,
            )  # fmt: skip
        )
    return out


def sentiment_gaps(ctx: _Ctx, rules: OpportunityRules) -> list[Opportunity]:
    t = ctx.target.brand_id
    tv = ctx.vis.get((ALL, t))
    best = _best_competitor(ctx, ALL, "positive_rate")
    if not tv or not best or tv.positive_rate is None:
        return []
    gap = best.positive_rate - tv.positive_rate
    if gap < rules.positive_gap:
        return []
    labelled = [m for m in ctx.inp.mentions if m.brand_id == t and m.sentiment]
    evidence = [m.response_id for m in labelled if m.sentiment in {"negative", "mixed", "neutral"}]
    comp = ctx.names[best.brand_id]
    return [
        _make(
            ctx,
            rules,
            "sentiment_gap",
            None,
            f"{ctx.target.name} is described less positively than {comp} "
            f"({_pct(tv.positive_rate)} vs {_pct(best.positive_rate)} positive)",
            f"Of {len(labelled)} labelled mentions of {ctx.target.name}, {len(evidence)} are "
            "neutral, mixed or negative. Labels come from the LLM step and should be spot-checked.",
            _retest(None, len({ctx.cat_of.get(r) for r in evidence})),
            gap,
            sample_size_confidence(len(labelled)),
            evidence,
            "positive_rate",
            tv.positive_rate,
            best.positive_rate,
            best.brand_id,
        )  # fmt: skip
    ]


def accuracy_issues(ctx: _Ctx, rules: OpportunityRules) -> list[Opportunity]:
    """Mismatches on facts about the target brand or any catalogue product."""
    by_fact: dict[str, list] = defaultdict(list)
    for c in ctx.inp.accuracy_checks:
        by_fact[c.fact_id].append(c)
    out = []
    for fact_id, checks in sorted(by_fact.items()):
        f = ctx.inp.facts.get(fact_id)
        if not f or (f.subject_type == "brand" and f.subject != ctx.target.name):
            continue
        mism = [c for c in checks if c.verdict == "mismatch"]
        decided = [c for c in checks if c.verdict in {"match", "mismatch"}]
        if not mism:
            continue
        stated = sorted({c.stated_value for c in mism if c.stated_value})[:3]
        out.append(
            _make(
                ctx,
                rules,
                "accuracy_issue",
                None,
                f"AI answers state '{f.attribute}' of {f.subject} incorrectly "
                f"({len(mism)} of {len(decided)} answers)",
                f"Verified value: {f.approved_value}. "
                f"Answers stated: {', '.join(stated) or 'n/a'}.",
                _retest(None, len(mism)),
                len(mism) / len(decided),
                sample_size_confidence(len(decided)),
                [c.response_id for c in mism],
                f"accuracy:{f.attribute}",
                None,
                None,
                None,
            )  # fmt: skip
        )
        out[-1].dedupe_key = f"accuracy_issue|{fact_id}"
    return out


def unstable_visibility(ctx: _Ctx, rules: OpportunityRules) -> list[Opportunity]:
    agree = ctx.inp.repeat_agreement
    if agree is None or agree >= rules.repeat_agreement:
        return []
    t = ctx.target.brand_id
    by_prompt: dict[str, list[str]] = defaultdict(list)
    for r in ctx.ok:
        by_prompt[r.prompt_id].append(r.response_id)
    evidence = [
        rid
        for ids in by_prompt.values()
        if len(ids) > 1 and len({(i, t) in ctx.mentioned for i in ids}) > 1
        for rid in ids
    ]
    return [
        _make(
            ctx,
            rules,
            "unstable_visibility",
            None,
            f"{ctx.target.name}'s presence is unstable across repeated questions "
            f"({_pct(agree)} agreement)",
            "The same question asked again often flips between mentioning and not mentioning "
            f"{ctx.target.name}. Single answers are unreliable; the brand is on the margin.",
            _retest(None, len({ctx.cat_of.get(r) for r in evidence})),
            1 - agree,
            sample_size_confidence(len(evidence)),
            evidence,
            "agreement_rate",
            agree,
        )  # fmt: skip
    ]


RULES = [
    visibility_gaps,
    ranking_gaps,
    citation_gaps,
    sentiment_gaps,
    accuracy_issues,
    unstable_visibility,
]


def find_gaps(inp: OpportunityInputs, rules: OpportunityRules) -> list[Opportunity]:
    ctx = _Ctx(inp)
    opps = [o for rule in RULES for o in rule(ctx, rules)]
    return sorted(opps, key=lambda o: o.priority_score, reverse=True)
