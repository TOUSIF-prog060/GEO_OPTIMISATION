"""Diagnostics engine entry points.

diagnose()          Bronze -> Silver (citations, brand + product mentions)
                    -> Gold (visibility, source share, repeatability). No API calls.
classify_mentions() Optional: LLM labels sentiment / is_recommended, then Gold is refreshed.
check_accuracy()    Optional: LLM extracts stated facts, rules compare them with the verified
                    reference facts -> silver_accuracy_checks -> gold_accuracy.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import AnalysisConfig, Settings
from src.diagnostics.accuracy import CHECKER_VERSION, compare_value, extract_claims
from src.diagnostics.classifier import label_mention
from src.diagnostics.metrics import (
    compute_accuracy,
    compute_repeatability,
    compute_source_share,
    compute_visibility,
)
from src.diagnostics.models import (
    AccuracyCheckRow,
    AccuracyInput,
    AccuracyOutput,
    ClassifyInput,
    ClassifyOutput,
    DiagnoseInput,
    DiagnoseOutput,
    FactRef,
    MentionLabel,
    MentionToLabel,
    ResponseRecord,
)
from src.diagnostics.parsing import parse_product_mentions, parse_response
from src.diagnostics.repository import DiagnosticsRepository

logger = logging.getLogger(__name__)

LabelFn = Callable[[AnalysisConfig, str, MentionToLabel], MentionLabel]
ExtractFn = Callable[
    [AnalysisConfig, str, str, list[FactRef], dict[str, str]], dict[str, str | None]
]


def diagnose(inp: DiagnoseInput, repo: DiagnosticsRepository) -> DiagnoseOutput:
    responses = repo.load_responses(inp.run_id)
    if not responses:
        raise ValueError(f"No responses for run {inp.run_id} (wrong run_id, or run is empty)")
    brands = repo.load_brands()
    if not brands:
        raise ValueError("No brands in the database. Run a discovery sync first.")
    domains = repo.load_domains()

    products = repo.load_products()

    ok = [r for r in responses if r.ok]
    citations, mentions, product_mentions = [], [], []
    for r in ok:
        c, m = parse_response(r, brands, inp.parser_version)
        citations.extend(c)
        mentions.extend(m)
        product_mentions.extend(parse_product_mentions(r, products, inp.parser_version))
    repo.save_silver(citations, mentions)
    repo.save_product_mentions(product_mentions)

    gold = refresh_gold(inp, repo, responses=responses, brands=brands, domains=domains)
    logger.info(
        "Diagnosed run %s: %d responses, %d citations, %d mention rows",
        inp.run_id, len(ok), len(citations), len(mentions),
    )  # fmt: skip
    return DiagnoseOutput(
        run_id=inp.run_id,
        n_responses=len(ok),
        n_skipped_errors=len(responses) - len(ok),
        n_citations=len(citations),
        n_mentions=sum(m.mentioned for m in mentions),
        n_visibility_rows=gold[0],
        n_source_rows=gold[1],
        n_product_mentions=len(product_mentions),
        n_repeatability_rows=gold[2],
    )


def refresh_gold(inp: DiagnoseInput, repo: DiagnosticsRepository, **loaded) -> tuple[int, int, int]:
    """Recompute Gold from what is stored in Silver (so LLM labels are included)."""
    responses = loaded.get("responses") or repo.load_responses(inp.run_id)
    brands = loaded.get("brands") or repo.load_brands()
    domains = loaded.get("domains") or repo.load_domains()
    mentions = repo.load_mentions(inp.run_id, inp.parser_version)
    citations = repo.load_citations(inp.run_id, inp.parser_version)
    vis = compute_visibility(
        inp.run_id, responses, mentions, citations, brands, domains, inp.metric_version
    )
    src = compute_source_share(inp.run_id, responses, citations, domains, inp.metric_version)
    rep_rows = compute_repeatability(inp.run_id, responses, mentions, brands, inp.metric_version)
    repo.save_gold(vis, src)
    repo.save_repeatability(rep_rows)
    return len(vis), len(src), len(rep_rows)


def classify_mentions(
    inp: ClassifyInput,
    settings: Settings,
    repo: DiagnosticsRepository,
    label_fn: LabelFn | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> ClassifyOutput:
    """Label every unlabelled mention in a run. Needs OPENAI_API_KEY."""
    api_key = settings.require("openai_api_key")
    cfg = settings.project.analysis
    fn = label_fn or label_mention
    items = repo.load_unlabelled(inp.run_id, inp.parser_version)
    n_ok = n_failed = 0
    with ThreadPoolExecutor(max_workers=inp.max_workers) as pool:
        futures = {pool.submit(fn, cfg, api_key, it): it for it in items}
        for done, fut in enumerate(as_completed(futures), start=1):
            item = futures[fut]
            try:
                label = fut.result()
            except Exception as exc:
                n_failed += 1
                logger.error("Labelling mention %s failed: %s", item.mention_id, exc)
            else:
                repo.save_label(item.mention_id, label, classified_by=cfg.model)
                n_ok += 1
            if on_progress:
                on_progress(done, len(items))
    if n_ok:
        refresh_gold(DiagnoseInput(run_id=inp.run_id, parser_version=inp.parser_version), repo)
    return ClassifyOutput(run_id=inp.run_id, n_classified=n_ok, n_failed=n_failed, model=cfg.model)


# ---------------------------------------------------------------- accuracy


def facts_for_response(
    resp: ResponseRecord,
    facts: list[FactRef],
    mentioned_brands: set[str],
    mentioned_products: set[str],
) -> list[FactRef]:
    """Only facts whose subject the answer actually mentions."""
    return [
        f
        for f in facts
        if (f.subject_type == "brand" and f.subject in mentioned_brands)
        or (f.subject_type == "product" and f.subject in mentioned_products)
    ]


def check_accuracy(
    inp: AccuracyInput,
    settings: Settings,
    repo: DiagnosticsRepository,
    extract_fn: ExtractFn | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    parser_version: str = "v1",
) -> AccuracyOutput:
    """Needs OPENAI_API_KEY, reference facts, and diagnose() to have run first."""
    api_key = settings.require("openai_api_key")
    cfg = settings.project.analysis
    fn = extract_fn or extract_claims
    facts = repo.load_facts()
    if not facts:
        raise ValueError("No reference facts. Fill data/reference/reference_facts_v1.csv first.")

    brands = {b.brand_id: b.name for b in repo.load_brands()}
    products = {p.product_id: p.product_name for p in repo.load_products()}
    names = {**{n: n for n in brands.values()}, **products}
    by_resp_brands: dict[str, set[str]] = {}
    for m in repo.load_mentions(inp.run_id, parser_version):
        if m.mentioned:
            by_resp_brands.setdefault(m.response_id, set()).add(brands[m.brand_id])
    by_resp_products: dict[str, set[str]] = {}
    for pm in repo.load_product_mentions(inp.run_id, parser_version):
        by_resp_products.setdefault(pm.response_id, set()).add(pm.product_id)

    work = []
    for r in repo.load_responses(inp.run_id):
        if not r.ok:
            continue
        wanted = facts_for_response(
            r,
            list(facts.values()),
            by_resp_brands.get(r.response_id, set()),
            by_resp_products.get(r.response_id, set()),
        )
        if wanted:
            work.append((r, wanted))

    checks: list[AccuracyCheckRow] = []
    n_failed = 0
    with ThreadPoolExecutor(max_workers=inp.max_workers) as pool:
        futures = {
            pool.submit(fn, cfg, api_key, r.answer_text or "", wanted, names): (r, wanted)
            for r, wanted in work
        }
        for done, fut in enumerate(as_completed(futures), start=1):
            r, wanted = futures[fut]
            try:
                stated = fut.result()
            except Exception as exc:
                n_failed += 1
                logger.error("Accuracy extraction failed for %s: %s", r.response_id, exc)
            else:
                checks.extend(
                    AccuracyCheckRow(
                        response_id=r.response_id,
                        run_id=r.run_id,
                        fact_id=f.fact_id,
                        stated_value=stated.get(f.fact_id),
                        approved_value=f.approved_value,
                        verdict=compare_value(stated.get(f.fact_id), f),
                        extracted_by=cfg.model,
                        checker_version=inp.checker_version or CHECKER_VERSION,
                    )
                    for f in wanted
                )
            if on_progress:
                on_progress(done, len(work))

    repo.save_accuracy(checks)
    stored = repo.load_accuracy_checks(inp.run_id, inp.checker_version)
    repo.save_gold_accuracy(compute_accuracy(inp.run_id, stored, facts, inp.metric_version))
    return AccuracyOutput(
        run_id=inp.run_id,
        n_responses_checked=len(work) - n_failed,
        n_checks=len(checks),
        n_failed=n_failed,
        model=cfg.model,
    )
