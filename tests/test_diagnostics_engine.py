import json
from types import SimpleNamespace
from typing import Any

import pytest

from src.config import AnalysisConfig, Settings, load_project_config
from src.diagnostics import ClassifyInput, DiagnoseInput, classify_mentions, diagnose
from src.diagnostics.classifier import build_label_request, label_mention, parse_label
from src.diagnostics.metrics import compute_source_share, compute_visibility
from src.diagnostics.models import (
    BrandRef,
    CitationRow,
    DomainRef,
    MentionLabel,
    MentionRow,
    MentionToLabel,
    ResponseRecord,
)
from src.diagnostics.reference import domains_path, load_domains_csv

BRANDS = [
    BrandRef(brand_id=1, name="Sephora India", aliases=["Sephora"], is_target=True),
    BrandRef(brand_id=2, name="Nykaa", aliases=["Nykaa"]),
]
DOMAINS = {
    "sephora.in": DomainRef(domain="sephora.in", domain_type="brand_owned", brand_id=1),
    "nykaa.com": DomainRef(domain="nykaa.com", domain_type="competitor", brand_id=2),
    "vogue.in": DomainRef(domain="vogue.in", domain_type="editorial"),
}


def pplx(text: str, cites: list[str]) -> dict:
    return {"choices": [{"message": {"content": text}}], "citations": cites}


def response(rid: str, category: str, text: str, cites: list[str], error: str | None = None):
    return ResponseRecord(
        response_id=rid,
        run_id="run1",
        prompt_id=rid,
        provider="perplexity",
        category=category,
        prompt_text=f"question {rid}",
        answer_text=None if error else text,
        raw_response=None if error else pplx(text, cites),
        error=error,
    )


RESPONSES = [
    response(
        "a", "retailer", "1. Nykaa\n2. Sephora", ["https://nykaa.com/x", "https://vogue.in/y"]
    ),
    response("b", "retailer", "Nykaa is good.", ["https://nykaa.com/z"]),
    response("c", "sunscreen", "Buy at Sephora.", ["https://sephora.in/s", "https://unknown.org"]),
    response("d", "sunscreen", "", [], error="HTTPStatusError: 500"),
]


class FakeRepo:
    def __init__(self) -> None:
        self.mentions: list[MentionRow] = []
        self.citations: list[CitationRow] = []
        self.vis: list = []
        self.src: list = []
        self.labels: dict[int, tuple[MentionLabel, str]] = {}
        self.products: list = []
        self.product_mentions: list = []
        self.repeatability: list = []
        self.facts: dict = {}
        self.checks: list = []
        self.gold_accuracy: list = []

    def load_responses(self, run_id: str):
        return RESPONSES if run_id == "run1" else []

    def load_brands(self):
        return BRANDS

    def load_domains(self):
        return DOMAINS

    def save_silver(self, citations, mentions):
        self.citations, self.mentions = list(citations), list(mentions)

    def load_mentions(self, run_id, parser_version):
        return self.mentions

    def load_citations(self, run_id, parser_version):
        return self.citations

    def save_gold(self, visibility, sources):
        self.vis, self.src = visibility, sources

    def load_unlabelled(self, run_id, parser_version):
        return [
            MentionToLabel(mention_id=i, brand_name="Nykaa", prompt_text="q", answer_text="a")
            for i, m in enumerate(self.mentions)
            if m.mentioned and m.sentiment is None
        ]

    def save_label(self, mention_id: int, label: MentionLabel, classified_by: str) -> None:
        self.labels[mention_id] = (label, classified_by)
        m = self.mentions[mention_id]
        self.mentions[mention_id] = m.model_copy(
            update={"sentiment": label.sentiment, "is_recommended": label.is_recommended}
        )

    def load_products(self):
        return self.products

    def load_facts(self):
        return self.facts

    def save_product_mentions(self, rows):
        self.product_mentions = list(rows)

    def load_product_mentions(self, run_id, parser_version):
        return self.product_mentions

    def save_repeatability(self, rows):
        self.repeatability = list(rows)

    def save_accuracy(self, checks):
        self.checks = list(checks)

    def load_accuracy_checks(self, run_id, checker_version):
        return self.checks

    def save_gold_accuracy(self, rows):
        self.gold_accuracy = list(rows)


def overall(rows, brand_id):
    return next(r for r in rows if r.brand_id == brand_id and r.category == "ALL")


def test_diagnose_end_to_end() -> None:
    repo = FakeRepo()
    out = diagnose(DiagnoseInput(run_id="run1"), repo)

    assert out.n_responses == 3 and out.n_skipped_errors == 1
    assert out.n_citations == 5
    assert len(repo.mentions) == 3 * 2  # one row per brand per successful response

    nykaa, sephora = overall(repo.vis, 2), overall(repo.vis, 1)
    assert nykaa.mention_rate == pytest.approx(2 / 3, abs=1e-4)
    assert sephora.mention_rate == pytest.approx(2 / 3, abs=1e-4)
    assert nykaa.share_of_voice == pytest.approx(0.5)
    assert nykaa.avg_rank == 1.0 and sephora.avg_rank == 2.0
    assert nykaa.citation_share == pytest.approx(2 / 5)
    assert sephora.citation_share == pytest.approx(1 / 5)
    assert nykaa.positive_rate is None  # no labels yet

    retail_sephora = next(r for r in repo.vis if r.brand_id == 1 and r.category == "retailer")
    assert retail_sephora.n_responses == 2 and retail_sephora.mention_rate == pytest.approx(0.5)


def test_source_share_classifies_and_flags_unknown() -> None:
    repo = FakeRepo()
    diagnose(DiagnoseInput(run_id="run1"), repo)
    all_rows = {s.domain: s for s in repo.src if s.category == "ALL"}
    assert all_rows["nykaa.com"].n_citations == 2
    assert all_rows["nykaa.com"].citation_share == pytest.approx(0.4)
    assert all_rows["unknown.org"].domain_type == "unclassified"


def test_diagnose_unknown_run() -> None:
    with pytest.raises(ValueError, match="No responses"):
        diagnose(DiagnoseInput(run_id="nope"), FakeRepo())


def test_metrics_handle_empty_denominators() -> None:
    rows = compute_visibility("r", RESPONSES[3:], [], [], BRANDS, DOMAINS)
    assert rows == []  # only an errored response: nothing to report
    assert compute_source_share("r", RESPONSES, [], DOMAINS) == []


def settings(key: str | None = "k") -> Settings:
    return Settings(project=load_project_config(), openai_api_key=key)


def test_classify_updates_labels_and_gold() -> None:
    repo = FakeRepo()
    diagnose(DiagnoseInput(run_id="run1"), repo)

    def fake_label(cfg, api_key, item):
        return MentionLabel(sentiment="positive", is_recommended=True)

    out = classify_mentions(ClassifyInput(run_id="run1"), settings(), repo, label_fn=fake_label)
    n_mentioned = sum(m.mentioned for m in repo.mentions)
    assert out.n_classified == n_mentioned and out.n_failed == 0
    assert all(by == settings().project.analysis.model for _, by in repo.labels.values())
    assert overall(repo.vis, 2).positive_rate == 1.0  # gold refreshed with labels


def test_classify_failures_counted_not_raised() -> None:
    repo = FakeRepo()
    diagnose(DiagnoseInput(run_id="run1"), repo)

    def broken(cfg, api_key, item):
        raise ValueError("bad json")

    out = classify_mentions(ClassifyInput(run_id="run1"), settings(), repo, label_fn=broken)
    assert out.n_classified == 0 and out.n_failed > 0


def test_classify_requires_key() -> None:
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        classify_mentions(ClassifyInput(run_id="run1"), settings(None), FakeRepo())


def test_label_request_and_parse_with_fake_client() -> None:
    item = MentionToLabel(
        mention_id=1, brand_name="Tira", prompt_text="q?", answer_text="Tira is ok"
    )
    req = build_label_request(AnalysisConfig(model="m"), item)
    assert req["text"]["format"]["strict"] is True and "Tira" in req["input"]

    raw = {"output": [{"type": "message", "content": [{"type": "output_text",
           "text": json.dumps({"sentiment": "neutral", "is_recommended": False})}]}]}  # fmt: skip
    captured: dict[str, Any] = {}

    def create(**kw):
        captured.update(kw)
        return SimpleNamespace(model_dump=lambda mode=None: raw)

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    label = label_mention(AnalysisConfig(model="m"), "k", item, client=client)
    assert label == MentionLabel(sentiment="neutral", is_recommended=False)
    assert captured["model"] == "m"


def test_parse_label_rejects_bad_values() -> None:
    raw = {"output": [{"type": "message", "content": [{"type": "output_text",
           "text": json.dumps({"sentiment": "great", "is_recommended": True})}]}]}  # fmt: skip
    with pytest.raises(ValueError):
        parse_label(raw)


def test_domains_v1_reference_is_valid() -> None:
    rows = load_domains_csv(domains_path("v1"))
    owned = [r for r in rows if r.domain_type == "brand_owned"]
    assert [r.brand_name for r in owned] == ["Sephora India"]
    assert len({r.domain for r in rows}) == len(rows)
