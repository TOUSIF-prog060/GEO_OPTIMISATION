"""Opportunity engine entry point: diagnostics (Gold + Silver) -> ranked opportunities
-> template recommendations awaiting human approval. No API calls."""

from __future__ import annotations

import logging
from collections import Counter

from src.opportunities.models import OpportunityInput, OpportunityOutput
from src.opportunities.recommend import recommend
from src.opportunities.repository import OpportunityRepository
from src.opportunities.rules import find_gaps

logger = logging.getLogger(__name__)


def find_opportunities(inp: OpportunityInput, repo: OpportunityRepository) -> OpportunityOutput:
    data = repo.load_inputs(inp.run_id)
    if not data.visibility:
        raise ValueError(f"No diagnostics for run {inp.run_id}. Run diagnostics first.")
    if not any(b.is_target for b in data.brands):
        raise ValueError("No target brand in the database.")
    names = {b.brand_id: b.name for b in data.brands}

    opps = find_gaps(data, inp.rules)
    ids: list[str] = []
    for rank, opp in enumerate(opps, start=1):
        opp.opportunity_id = repo.save_opportunity(opp)
        ids.append(opp.opportunity_id)
        rec = recommend(opp, data.target.name, names.get(opp.benchmark_brand_id or -1))
        rec.priority = rank
        repo.save_recommendation(rec)
    logger.info("Run %s: %d opportunities", inp.run_id, len(opps))
    return OpportunityOutput(
        run_id=inp.run_id,
        n_opportunities=len(opps),
        n_recommendations=len(opps),
        by_type=dict(Counter(o.gap_type for o in opps)),
        opportunity_ids=ids,
    )
