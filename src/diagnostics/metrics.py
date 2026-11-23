"""Gold metrics, computed with plain Python from Silver rows (no LLM, fully reproducible).

Definitions (per run x category; category 'ALL' covers the whole run). Only successful
responses count.
  mention_rate   = responses mentioning the brand / responses
  share_of_voice = responses mentioning the brand / sum of that count over all tracked brands
  avg_rank       = mean rank_in_list where the brand appears in a list
  citation_share = citations to domains owned by the brand / all citations
  positive_rate  = mentions labelled 'positive' / mentions with any sentiment label
                   (None until the optional LLM labelling step has run)
Repeatability (per run x brand, prompts asked 2+ times):
  agreement_rate        = prompts where every repeat agrees on mentioned / not mentioned
  mean_within_prompt_sd = mean population SD of the 0/1 mention indicator across repeats
Accuracy (per run x subject x attribute):
  accuracy_rate = match / (match + mismatch); not_mentioned and unverifiable are reported
                  separately and excluded from the rate
Bump METRIC_VERSION whenever a definition changes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean, pstdev

from src.diagnostics.models import (
    AccuracyCheckRow,
    AccuracyRow,
    BrandRef,
    CitationRow,
    DomainRef,
    FactRef,
    MentionRow,
    RepeatabilityRow,
    ResponseRecord,
    SourceShareRow,
    VisibilityRow,
)
from src.diagnostics.parsing import classify_domain

METRIC_VERSION = "v1"
ALL = "ALL"


def _ratio(num: int, den: int, digits: int = 4) -> float | None:
    return round(num / den, digits) if den else None


def group_responses(responses: list[ResponseRecord]) -> dict[str, set[str]]:
    """category -> response_ids (successful responses only), plus 'ALL'."""
    groups: dict[str, set[str]] = defaultdict(set)
    for r in responses:
        if r.ok:
            groups[r.category].add(r.response_id)
            groups[ALL].add(r.response_id)
    return dict(groups)


def compute_visibility(
    run_id: str,
    responses: list[ResponseRecord],
    mentions: list[MentionRow],
    citations: list[CitationRow],
    brands: list[BrandRef],
    domains: dict[str, DomainRef],
    metric_version: str = METRIC_VERSION,
) -> list[VisibilityRow]:
    rows: list[VisibilityRow] = []
    for category, ids in sorted(group_responses(responses).items()):
        cat_mentions = [m for m in mentions if m.response_id in ids and m.mentioned]
        cat_cites = [c for c in citations if c.response_id in ids]
        mentioned_by_brand = Counter(m.brand_id for m in cat_mentions)
        total_mentioned = sum(mentioned_by_brand.values())
        cite_owner = Counter(
            ref.brand_id
            for c in cat_cites
            if (ref := classify_domain(c.domain, domains)) and ref.brand_id is not None
        )
        for b in brands:
            bm = [m for m in cat_mentions if m.brand_id == b.brand_id]
            ranks = [m.rank_in_list for m in bm if m.rank_in_list is not None]
            labelled = [m for m in bm if m.sentiment is not None]
            rows.append(
                VisibilityRow(
                    run_id=run_id,
                    brand_id=b.brand_id,
                    category=category,
                    n_responses=len(ids),
                    mention_rate=_ratio(mentioned_by_brand[b.brand_id], len(ids)),
                    share_of_voice=_ratio(mentioned_by_brand[b.brand_id], total_mentioned),
                    avg_rank=round(mean(ranks), 2) if ranks else None,
                    citation_share=_ratio(cite_owner[b.brand_id], len(cat_cites)),
                    positive_rate=_ratio(
                        sum(m.sentiment == "positive" for m in labelled), len(labelled)
                    ),
                    metric_version=metric_version,
                )
            )
    return rows


def compute_source_share(
    run_id: str,
    responses: list[ResponseRecord],
    citations: list[CitationRow],
    domains: dict[str, DomainRef],
    metric_version: str = METRIC_VERSION,
) -> list[SourceShareRow]:
    rows: list[SourceShareRow] = []
    for category, ids in sorted(group_responses(responses).items()):
        counts = Counter(c.domain for c in citations if c.response_id in ids)
        total = sum(counts.values())
        for domain, n in counts.most_common():
            ref = classify_domain(domain, domains)
            rows.append(
                SourceShareRow(
                    run_id=run_id,
                    category=category,
                    domain=domain,
                    domain_type=ref.domain_type if ref else "unclassified",
                    n_citations=n,
                    citation_share=round(n / total, 4),
                    metric_version=metric_version,
                )
            )
    return rows


def compute_repeatability(
    run_id: str,
    responses: list[ResponseRecord],
    mentions: list[MentionRow],
    brands: list[BrandRef],
    metric_version: str = METRIC_VERSION,
) -> list[RepeatabilityRow]:
    """Empty when no prompt was asked more than once."""
    by_prompt: dict[str, list[str]] = defaultdict(list)
    for r in responses:
        if r.ok:
            by_prompt[r.prompt_id].append(r.response_id)
    repeated = {p: ids for p, ids in by_prompt.items() if len(ids) >= 2}
    if not repeated:
        return []
    mentioned = {(m.response_id, m.brand_id) for m in mentions if m.mentioned}
    rows: list[RepeatabilityRow] = []
    for b in brands:
        agree, sds = 0, []
        for ids in repeated.values():
            flags = [int((rid, b.brand_id) in mentioned) for rid in ids]
            agree += len(set(flags)) == 1
            sds.append(pstdev(flags))
        rows.append(
            RepeatabilityRow(
                run_id=run_id,
                brand_id=b.brand_id,
                n_prompts=len(repeated),
                agreement_rate=_ratio(agree, len(repeated)),
                mean_within_prompt_sd=round(mean(sds), 4),
                metric_version=metric_version,
            )
        )
    return rows


def compute_accuracy(
    run_id: str,
    checks: list[AccuracyCheckRow],
    facts: dict[str, FactRef],
    metric_version: str = METRIC_VERSION,
) -> list[AccuracyRow]:
    groups: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for c in checks:
        f = facts.get(c.fact_id)
        if f:
            groups[(f.subject, f.attribute)][c.verdict] += 1
    rows: list[AccuracyRow] = []
    for (subject, attribute), n in sorted(groups.items()):
        rows.append(
            AccuracyRow(
                run_id=run_id,
                subject=subject,
                attribute=attribute,
                n_checked=sum(n.values()),
                n_match=n["match"],
                n_mismatch=n["mismatch"],
                n_not_mentioned=n["not_mentioned"],
                n_unverifiable=n["unverifiable"],
                accuracy_rate=_ratio(n["match"], n["match"] + n["mismatch"]),
                metric_version=metric_version,
            )
        )
    return rows
