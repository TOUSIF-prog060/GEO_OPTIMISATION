"""Offline evaluation suites: measurement accuracy, metric correctness, gap detection.

Every suite returns a dict with `metrics` (numbers) and `failures` (cases that went wrong),
so the report can show both the score and why it is not perfect.
"""

from __future__ import annotations

from statistics import mean
from typing import Any

from evals.gold import MENTION_CASES, URL_CASES, N, S, T
from src.config import load_project_config
from src.diagnostics.metrics import compute_repeatability, compute_visibility
from src.diagnostics.models import BrandRef, CitationRow, DomainRef, ResponseRecord
from src.diagnostics.parsing import classify_domain, normalise_domain, parse_mentions
from src.diagnostics.reference import domains_path, load_domains_csv
from src.opportunities.models import GoldVisibility, OpportunityInputs, OpportunityRules
from src.opportunities.rules import find_gaps

# ---------------------------------------------------------------- shared fixtures


def brands() -> list[BrandRef]:
    cfg = load_project_config()
    return [BrandRef(brand_id=i, name=b.name, aliases=b.aliases, is_target=b.is_target)
            for i, b in enumerate(cfg.brands, start=1)]  # fmt: skip


def domains() -> dict[str, DomainRef]:
    ids = {b.name: b.brand_id for b in brands()}
    return {r.domain: DomainRef(domain=r.domain, domain_type=r.domain_type,
                                brand_id=ids.get(r.brand_name or ""))
            for r in load_domains_csv(domains_path("v1"))}  # fmt: skip


def response(rid: str, text: str, prompt_id: str = "P1", category: str = "eval",
             repeat_no: int = 1, run_id: str = "sandbox") -> ResponseRecord:  # fmt: skip
    return ResponseRecord(response_id=rid, run_id=run_id, prompt_id=prompt_id, provider="eval",
                          category=category, repeat_no=repeat_no, answer_text=text,
                          raw_response={"sandbox": True})  # fmt: skip


def prf(tp: int, fp: int, fn: int) -> dict[str, float | None]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"precision": p, "recall": r, "f1": f}


# ---------------------------------------------------------------- 1. measurement accuracy


def eval_measurement() -> dict[str, Any]:
    """Mention detection (P/R/F1), rank extraction, citation domain parsing."""
    bs = brands()
    names = {b.brand_id: b.name for b in bs}
    tp = fp = fn = tn = 0
    rank_pairs: list[tuple[int | None, int | None]] = []  # (truth, predicted) where both mentioned
    failures: list[dict[str, Any]] = []
    per_tag: dict[str, bool] = {}
    decisions: list[dict[str, Any]] = []  # every brand decision, for manual review
    url_results: list[dict[str, Any]] = []

    for case in MENTION_CASES:
        rows = parse_mentions(response(case.case_id, case.text), bs, "eval")
        ok = True
        for m in rows:
            brand = names[m.brand_id]
            truth = brand in case.expect
            decisions.append({
                "case": case.case_id, "tag": case.tag, "brand": brand,
                "truth_mentioned": truth, "pred_mentioned": m.mentioned,
                "truth_rank": (case.expect.get(brand) or None) if truth else None,
                "pred_rank": m.rank_in_list,
            })  # fmt: skip
            if truth and m.mentioned:
                tp += 1
                want = case.expect[brand] or None
                rank_pairs.append((want, m.rank_in_list))
                if want != m.rank_in_list:
                    ok = False
                    failures.append(
                        {
                            "case": case.case_id,
                            "tag": case.tag,
                            "brand": brand,
                            "issue": "rank",
                            "expected": want,
                            "got": m.rank_in_list,
                        }
                    )
            elif truth:
                fn += 1
                ok = False
                failures.append(
                    {
                        "case": case.case_id,
                        "tag": case.tag,
                        "brand": brand,
                        "issue": "missed mention",
                    }
                )
            elif m.mentioned:
                fp += 1
                ok = False
                failures.append(
                    {
                        "case": case.case_id,
                        "tag": case.tag,
                        "brand": brand,
                        "issue": "false mention",
                    }
                )
            else:
                tn += 1
        per_tag[case.tag] = ok

    ranked = [(t, p) for t, p in rank_pairs if t is not None]
    unranked = [(t, p) for t, p in rank_pairs if t is None]
    errors = [abs(t - p) for t, p in ranked if p is not None]

    doms = domains()
    dom_ok = own_ok = 0
    for u in URL_CASES:
        got = normalise_domain(u.url)
        dom_ok += got == u.domain
        ref = classify_domain(got, doms) if got else None
        owner = next((b.name for b in brands() if ref and b.brand_id == ref.brand_id), None)
        own_ok += owner == u.owner
        url_results.append({"url": u.url, "expected_domain": u.domain, "got_domain": got,
                            "expected_owner": u.owner, "got_owner": owner})  # fmt: skip
        if got != u.domain or owner != u.owner:
            failures.append(
                {
                    "case": u.url,
                    "tag": "citation",
                    "issue": "domain",
                    "expected": f"{u.domain} / {u.owner}",
                    "got": f"{got} / {owner}",
                }
            )

    return {
        "metrics": {
            "cases": len(MENTION_CASES),
            "brand_decisions": tp + fp + fn + tn,
            "mention": prf(tp, fp, fn) | {"accuracy": (tp + tn) / (tp + fp + fn + tn),
                                          "tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "rank": {
                "exact_match": sum(t == p for t, p in rank_pairs) / len(rank_pairs),
                "ranked_found": sum(p is not None for _, p in ranked) / len(ranked),
                "ranked_exact": sum(t == p for t, p in ranked) / len(ranked),
                "mean_abs_error": mean(errors) if errors else None,
                "spurious_rank_rate": sum(p is not None for _, p in unranked) / len(unranked),
                "n_ranked": len(ranked),
                "n_unranked": len(unranked),
            },
            "citations": {
                "domain_accuracy": dom_ok / len(URL_CASES),
                "owner_accuracy": own_ok / len(URL_CASES),
                "n": len(URL_CASES),
            },
            "cases_fully_correct": sum(per_tag.values()) / len(per_tag),
        },
        "decisions": decisions,
        "urls": url_results,
        "failures": failures,
    }  # fmt: skip


# ---------------------------------------------------------------- 2. metric correctness


def eval_metrics() -> dict[str, Any]:
    """Known answers in, hand-computed metrics out. Any difference is a calculation bug."""
    bs = brands()
    ids = {b.name: b.brand_id for b in bs}
    texts = [
        "1. Nykaa\n2. Sephora India",  # S rank 2, N rank 1
        "1. Sephora India\n2. Tira\n3. Nykaa",  # S1 T2 N3
        "Nykaa is the usual choice.",  # N only, no rank
        "Buy from brand websites.",  # nobody
    ]
    resps = [response(f"r{i}", t, prompt_id=f"P{i}") for i, t in enumerate(texts)]
    mentions = [m for r in resps for m in parse_mentions(r, bs, "eval")]
    cites = [
        CitationRow(response_id="r0", run_id="sandbox", position=1, url="https://nykaa.com/a",
                    domain="nykaa.com", parser_version="eval"),
        CitationRow(response_id="r1", run_id="sandbox", position=1, url="https://sephora.in/b",
                    domain="sephora.in", parser_version="eval"),
        CitationRow(response_id="r1", run_id="sandbox", position=2, url="https://reddit.com/c",
                    domain="reddit.com", parser_version="eval"),
        CitationRow(response_id="r2", run_id="sandbox", position=1, url="https://nykaa.com/d",
                    domain="nykaa.com", parser_version="eval"),
    ]  # fmt: skip
    rows = {(r.brand_id, r.category): r for r in
            compute_visibility("sandbox", resps, mentions, cites, bs, domains())}  # fmt: skip
    # Hand-computed: 4 answers; mentions S=2, N=3, T=1 (6 in total); citations 4 (N 2, S 1).
    expected = {
        S: {"mention_rate": 0.5, "share_of_voice": round(2 / 6, 4), "avg_rank": 1.5,
            "citation_share": 0.25},
        N: {"mention_rate": 0.75, "share_of_voice": 0.5, "avg_rank": 2.0, "citation_share": 0.5},
        T: {"mention_rate": 0.25, "share_of_voice": round(1 / 6, 4), "avg_rank": 2.0,
            "citation_share": 0.0},
    }  # fmt: skip
    checks, failures, table = 0, [], []
    for brand, want in expected.items():
        got = rows[(ids[brand], "ALL")]
        for k, v in want.items():
            checks += 1
            table.append({"brand": brand, "metric": k, "expected": v, "got": getattr(got, k)})
            if abs((getattr(got, k) or 0) - v) > 1e-4:
                failures.append({"brand": brand, "metric": k, "expected": v,
                                 "got": getattr(got, k)})  # fmt: skip

    # Repeatability: P1 asked 3 times; S mentioned 3/3 (agree), N 2/3 (disagree).
    rep_resps = [response(f"x{i}", t, prompt_id="P1", repeat_no=i)
                 for i, t in enumerate(["Sephora India, Nykaa", "Sephora India, Nykaa",
                                        "Sephora India"], 1)]  # fmt: skip
    rep_m = [m for r in rep_resps for m in parse_mentions(r, bs, "eval")]
    rep = {r.brand_id: r for r in compute_repeatability("sandbox", rep_resps, rep_m, bs)}
    for brand, want in {S: 1.0, N: 0.0, T: 1.0}.items():
        checks += 1
        table.append(
            {
                "brand": brand,
                "metric": "agreement_rate",
                "expected": want,
                "got": rep[ids[brand]].agreement_rate,
            }
        )
        if rep[ids[brand]].agreement_rate != want:
            failures.append({"brand": brand, "metric": "agreement_rate", "expected": want,
                             "got": rep[ids[brand]].agreement_rate})  # fmt: skip
    return {"metrics": {"checks": checks, "correct": checks - len(failures),
                        "accuracy": (checks - len(failures)) / checks},
            "checks": table, "failures": failures}  # fmt: skip


# ---------------------------------------------------------------- 3. gap detection


def _scenario(name: str, answers: list[tuple[str, str]], cites: list[tuple[int, str]] = (),
              repeat_agreement: float | None = None) -> OpportunityInputs:  # fmt: skip
    """answers: (category, text). cites: (answer index, domain)."""
    bs = brands()
    resps = [response(f"{name}-{i}", t, prompt_id=f"{name}-P{i}", category=c, run_id=name)
             for i, (c, t) in enumerate(answers)]  # fmt: skip
    mentions = [m for r in resps for m in parse_mentions(r, bs, "eval")]
    citations = [CitationRow(response_id=f"{name}-{i}", run_id=name, position=j + 1,
                             url=f"https://{d}/x", domain=d, parser_version="eval")
                 for j, (i, d) in enumerate(cites)]  # fmt: skip
    vis = compute_visibility(name, resps, mentions, citations, bs, domains())
    return OpportunityInputs(
        run_id=name, brands=bs, responses=resps, mentions=mentions, citations=citations,
        domains=domains(), repeat_agreement=repeat_agreement,
        visibility=[GoldVisibility(brand_id=v.brand_id, category=v.category,
                                   n_responses=v.n_responses, mention_rate=v.mention_rate,
                                   avg_rank=v.avg_rank, citation_share=v.citation_share,
                                   positive_rate=v.positive_rate) for v in vis],
    )  # fmt: skip


def gap_scenarios() -> list[tuple[str, OpportunityInputs, set[tuple[str, str | None]]]]:
    """(name, inputs, expected gaps as (gap_type, category)). Empty set = no gap should fire.
    Rules work per category by design (the "ALL" bucket never produces a gap)."""
    serum_missing = [("serum", "1. Nykaa\n2. Tira")] * 8 + [
        ("serum", "1. Nykaa\n2. Sephora India\n3. Tira")
    ] * 2
    balanced = [
        ("makeup", t)
        for t in [
            "1. Nykaa\n2. Sephora India\n3. Tira",
            "1. Sephora India\n2. Tira\n3. Nykaa",
            "1. Tira\n2. Nykaa\n3. Sephora India",
        ]
        * 3
    ]
    ranked_low = [("retailer", "1. Nykaa\n2. Tira\n3. Sephora India")] * 6
    too_small = [("fragrance", "1. Nykaa")] * 2
    cited_less = [("skincare", "Nykaa, Sephora India and Tira all sell it.")] * 6
    nykaa_cited = [(i, "nykaa.com") for i in range(6)] + [(0, "sephora.in")]
    return [
        ("visibility_gap", _scenario("vis", serum_missing), {("visibility_gap", "serum")}),
        ("balanced_no_gap", _scenario("bal", balanced), set()),
        ("ranking_gap", _scenario("rank", ranked_low), {("ranking_gap", "retailer")}),
        ("small_sample_no_gap", _scenario("small", too_small), set()),
        ("citation_gap", _scenario("cite", cited_less, cites=nykaa_cited),
         {("citation_gap", "skincare")}),
        ("unstable_visibility", _scenario("unst", balanced, repeat_agreement=0.5),
         {("unstable_visibility", None)}),
    ]  # fmt: skip


def _label_gaps(gaps: set[tuple[str, str | None]]) -> list[str]:
    """Readable labels, e.g. 'visibility gap · serum'."""
    return sorted(f"{t.replace('_', ' ')} · {c or 'overall'}" for t, c in gaps) or ["no gap"]


def eval_gaps() -> dict[str, Any]:
    rules = OpportunityRules()
    tp = fp = fn = 0
    scenarios_ok = 0
    failures, table = [], []
    for name, inp, want in gap_scenarios():
        got = {(o.gap_type, o.category) for o in find_gaps(inp, rules)}
        hit, extra, miss = got & want, got - want, want - got
        tp, fp, fn = tp + len(hit), fp + len(extra), fn + len(miss)
        scenarios_ok += not extra and not miss
        table.append({"scenario": name, "expected": _label_gaps(want), "found": _label_gaps(got),
                      "correct": not extra and not miss})  # fmt: skip
        if extra or miss:
            failures.append({"scenario": name, "missed": sorted(map(str, miss)),
                             "unexpected": sorted(map(str, extra))})  # fmt: skip
    n = len(gap_scenarios())
    return {"metrics": prf(tp, fp, fn) | {"scenarios": n, "scenarios_correct": scenarios_ok,
                                         "tp": tp, "fp": fp, "fn": fn},
            "scenarios": table, "failures": failures}  # fmt: skip
