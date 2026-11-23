"""Template recommendations v1: one deterministic, evidence-linked action per opportunity.
The Content Copilot (Phase 4) turns approved recommendations into drafts."""

from __future__ import annotations

from src.opportunities.models import Opportunity, Recommendation

GENERATED_BY = "template_v1"

ACTIONS = {
    "visibility_gap": (
        "Publish or strengthen a '{cat}' page on {brand}'s site that directly answers the "
        "questions in the evidence (buying guide + FAQ), with clear product range, price "
        "points and availability, so answer engines have a citable {brand} source."
    ),
    "ranking_gap": (
        "Make {brand}'s differentiators for '{cat}' explicit and verifiable (range, authenticity, "
        "offers, delivery) on pages that answer engines already cite; compare honestly with "
        "alternatives rather than claiming superiority."
    ),
    "citation_gap": (
        "Audit which {comp} pages are cited for '{cat}' and create {brand} pages that cover the "
        "same intents with better structure (headings, FAQs, specs, structured data) so they "
        "can be cited."
    ),
    "sentiment_gap": (
        "Review the neutral/negative snippets in the evidence, check what public sources say "
        "about {brand}, and address genuine issues (policies, service information) on official "
        "pages. Do not create artificial reviews."
    ),
    "accuracy_issue": (
        "Correct or clarify the verified fact on {brand}'s official pages and key third-party "
        "listings so the correct value is easy to find and consistent everywhere."
    ),
    "unstable_visibility": (
        "Consolidate {brand}'s coverage of the affected topics into fewer, authoritative pages "
        "and monitor with repeated runs; instability means the brand is on the margin of being "
        "included."
    ),
}


def recommend(opp: Opportunity, brand_name: str, comp_name: str | None) -> Recommendation:
    if opp.opportunity_id is None:
        raise ValueError("Opportunity must be saved before recommending")
    action = ACTIONS[opp.gap_type].format(
        brand=brand_name, comp=comp_name or "competitor", cat=opp.category or "these topics"
    )
    return Recommendation(
        opportunity_id=opp.opportunity_id,
        action=action,
        rationale=opp.rationale,
        priority=0,  # set by rank in the engine
        generated_by=GENERATED_BY,
        evidence_response_ids=opp.evidence_response_ids,
    )
