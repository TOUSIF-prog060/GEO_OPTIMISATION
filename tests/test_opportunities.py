import pytest

from src.common.stats import (
    diff_ci,
    one_sided_p,
    sample_size_confidence,
    two_proportion_z,
    wilson_ci,
)
from src.diagnostics.models import (
    AccuracyCheckRow,
    BrandRef,
    CitationRow,
    DomainRef,
    FactRef,
    MentionRow,
    ResponseRecord,
)
from src.opportunities import OpportunityInput, OpportunityRules, find_opportunities
from src.opportunities.models import GoldVisibility, OpportunityInputs
from src.opportunities.recommend import recommend
from src.opportunities.rules import find_gaps, priority

SEPH, NYK = 1, 2
BRANDS = [
    BrandRef(brand_id=SEPH, name="Sephora India", aliases=["Sephora"], is_target=True),
    BrandRef(brand_id=NYK, name="Nykaa", aliases=["Nykaa"]),
]
DOMAINS = {
    "sephora.in": DomainRef(domain="sephora.in", domain_type="brand_owned", brand_id=SEPH),
    "nykaa.com": DomainRef(domain="nykaa.com", domain_type="competitor", brand_id=NYK),
}


def resp(i: int, cat: str, prompt: str | None = None) -> ResponseRecord:
    return ResponseRecord(
        response_id=f"r{i:02d}", run_id="run1", prompt_id=prompt or f"P{i}", provider="perplexity",
        category=cat, answer_text="x", raw_response={"x": 1},
    )  # fmt: skip


def m(i: int, brand: int, mentioned: bool, rank: int | None = None, sentiment=None) -> MentionRow:
    return MentionRow(
        response_id=f"r{i:02d}", run_id="run1", brand_id=brand, mentioned=mentioned,
        rank_in_list=rank, sentiment=sentiment, parser_version="v1",
    )  # fmt: skip


def scenario() -> OpportunityInputs:
    """sunscreen: Nykaa in 9/10 answers ranked 1st, Sephora in 2/10 ranked 3rd.
    retailer: both in 5/5 (no gap). Citations: nykaa.com in 8 sunscreen answers."""
    responses = [resp(i, "sunscreen") for i in range(10)] + [
        resp(i, "retailer") for i in range(10, 15)
    ]
    mentions = []
    for i in range(10):
        mentions.append(m(i, NYK, i < 9, rank=1 if i < 9 else None))
        mentions.append(m(i, SEPH, i < 2, rank=3 if i < 2 else None))
    for i in range(10, 15):
        mentions += [m(i, NYK, True, 1), m(i, SEPH, True, 2)]
    citations = [
        CitationRow(response_id=f"r{i:02d}", run_id="run1", position=1,
                    url="https://nykaa.com/x", domain="nykaa.com", parser_version="v1")
        for i in range(8)
    ]  # fmt: skip
    vis = [
        GoldVisibility(brand_id=NYK, category="sunscreen", n_responses=10, mention_rate=0.9,
                       avg_rank=1.0, citation_share=1.0),
        GoldVisibility(brand_id=SEPH, category="sunscreen", n_responses=10, mention_rate=0.2,
                       avg_rank=3.0, citation_share=0.0),
        GoldVisibility(brand_id=NYK, category="retailer", n_responses=5, mention_rate=1.0,
                       avg_rank=1.0, citation_share=None),
        GoldVisibility(brand_id=SEPH, category="retailer", n_responses=5, mention_rate=1.0,
                       avg_rank=2.0, citation_share=None),
        GoldVisibility(brand_id=NYK, category="ALL", n_responses=15, mention_rate=0.93),
        GoldVisibility(brand_id=SEPH, category="ALL", n_responses=15, mention_rate=0.47),
    ]  # fmt: skip
    return OpportunityInputs(
        run_id="run1", brands=BRANDS, responses=responses, visibility=vis,
        mentions=mentions, citations=citations, domains=DOMAINS,
    )  # fmt: skip


def by_type(opps, t, cat=None):
    return [o for o in opps if o.gap_type == t and (cat is None or o.category == cat)]


# ---------------------------------------------------------------- stats


def test_stats_helpers() -> None:
    z, p = two_proportion_z(9, 10, 2, 10)
    assert z > 3 and p < 0.01
    assert one_sided_p(9, 10, 2, 10) < 0.001
    assert two_proportion_z(0, 0, 1, 1) == (None, None)
    lo, hi = diff_ci(9, 10, 2, 10)
    assert lo < 0.7 < hi
    lo, hi = wilson_ci(0, 10)
    assert lo == 0 and 0 < hi < 0.35
    assert sample_size_confidence(10) == 0.5 and sample_size_confidence(0) == 0.0


# ---------------------------------------------------------------- rules


def test_visibility_gap_found_with_evidence_and_confidence() -> None:
    opps = find_gaps(scenario(), OpportunityRules())
    (vg,) = by_type(opps, "visibility_gap")
    assert vg.category == "sunscreen"
    assert vg.severity == pytest.approx(0.7)
    assert vg.confidence > 0.99  # 9/10 vs 2/10 is highly significant
    assert vg.evidence_response_ids == [f"r{i:02d}" for i in range(2, 9)]
    assert vg.benchmark_brand_id == NYK and "Nykaa" in vg.title
    assert "Experimentation Lab" in vg.validation_approach
    assert not by_type(opps, "visibility_gap", "retailer")  # no gap there


def test_ranking_and_citation_gaps() -> None:
    opps = find_gaps(scenario(), OpportunityRules())
    (rg,) = by_type(opps, "ranking_gap", "sunscreen")
    assert rg.evidence_response_ids == ["r00", "r01"]  # both listed, Sephora lower
    assert by_type(opps, "ranking_gap", "retailer")  # 2.0 vs 1.0 = gap of 1
    (cg,) = by_type(opps, "citation_gap")
    assert cg.severity == 1.0 and len(cg.evidence_response_ids) == 8
    assert cg.effort == "high"


def test_sorted_by_priority_and_priority_formula() -> None:
    opps = find_gaps(scenario(), OpportunityRules())
    scores = [o.priority_score for o in opps]
    assert scores == sorted(scores, reverse=True)
    assert priority(0.5, 1.0, "low") == 50 and priority(0.5, 1.0, "high") == pytest.approx(16.67)


def test_thresholds_and_min_responses() -> None:
    strict = OpportunityRules(mention_gap=0.8, rank_gap=5, citation_gap=1.1)
    assert not find_gaps(scenario(), strict)
    assert not by_type(find_gaps(scenario(), OpportunityRules(min_responses=50)), "visibility_gap")


def test_sentiment_accuracy_and_stability_rules() -> None:
    data = scenario()
    data.visibility += [
        GoldVisibility(brand_id=SEPH, category="ALL", n_responses=15, positive_rate=0.2),
        GoldVisibility(brand_id=NYK, category="ALL", n_responses=15, positive_rate=0.8),
    ]
    data.visibility = [
        v for v in data.visibility if not (v.category == "ALL" and v.positive_rate is None)
    ]
    data.mentions.append(m(10, SEPH, True, sentiment="negative"))
    data.facts = {
        "F1": FactRef(
            fact_id="F1",
            subject_type="brand",
            subject="Sephora India",
            attribute="offers_cod",
            approved_value="true",
            value_type="boolean",
        )
    }
    data.accuracy_checks = [
        AccuracyCheckRow(response_id=f"r1{i}", run_id="run1", fact_id="F1", stated_value=v,
                         approved_value="true", verdict=verdict, checker_version="v1")
        for i, (v, verdict) in enumerate(
            [("no", "mismatch"), ("yes", "match"), (None, "not_mentioned")]
        )
    ]  # fmt: skip
    data.repeat_agreement = 0.5
    opps = find_gaps(data, OpportunityRules())

    (sg,) = by_type(opps, "sentiment_gap")
    assert sg.severity == pytest.approx(0.6) and "r10" in sg.evidence_response_ids
    (ai,) = by_type(opps, "accuracy_issue")
    assert ai.severity == 0.5 and ai.evidence_response_ids == ["r10"] and ai.effort == "low"
    assert ai.dedupe_key == "accuracy_issue|F1"
    (uv,) = by_type(opps, "unstable_visibility")
    assert uv.severity == 0.5


def test_competitor_fact_is_not_an_opportunity() -> None:
    data = scenario()
    data.facts = {
        "F9": FactRef(
            fact_id="F9",
            subject_type="brand",
            subject="Nykaa",
            attribute="x",
            approved_value="1",
            value_type="number",
        )
    }
    data.accuracy_checks = [AccuracyCheckRow(response_id="r00", run_id="run1", fact_id="F9",
                                             stated_value="2", approved_value="1",
                                             verdict="mismatch", checker_version="v1")]  # fmt: skip
    assert not by_type(find_gaps(data, OpportunityRules()), "accuracy_issue")


# ---------------------------------------------------------------- engine + recommendations


class FakeRepo:
    def __init__(self, data: OpportunityInputs) -> None:
        self.data = data
        self.opps: dict[str, object] = {}
        self.recs: list = []

    def load_inputs(self, run_id):
        return self.data

    def save_opportunity(self, opp):
        oid = f"opp-{opp.dedupe_key}"
        self.opps[oid] = opp
        return oid

    def save_recommendation(self, rec):
        self.recs.append(rec)
        return f"rec-{len(self.recs)}"


def test_engine_saves_ranked_recommendations() -> None:
    repo = FakeRepo(scenario())
    out = find_opportunities(OpportunityInput(run_id="run1"), repo)
    assert out.n_opportunities == len(repo.opps) == len(repo.recs) > 0
    assert [r.priority for r in repo.recs] == list(range(1, len(repo.recs) + 1))
    first = repo.recs[0]
    assert first.generated_by == "template_v1" and "Sephora India" in first.action
    assert first.evidence_response_ids  # evidence carried to the recommendation


def test_engine_requires_diagnostics() -> None:
    data = scenario()
    data.visibility = []
    with pytest.raises(ValueError, match="Run diagnostics first"):
        find_opportunities(OpportunityInput(run_id="run1"), FakeRepo(data))


def test_recommend_requires_saved_opportunity() -> None:
    opp = find_gaps(scenario(), OpportunityRules())[0]
    with pytest.raises(ValueError):
        recommend(opp, "Sephora India", "Nykaa")
