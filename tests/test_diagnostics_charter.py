"""Charter v2.0 Phase 2 additions: products, repeatability, accuracy, reference data."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import AnalysisConfig, Settings, load_project_config
from src.diagnostics import AccuracyInput, DiagnoseInput, check_accuracy, diagnose
from src.diagnostics.accuracy import (
    build_extract_request,
    compare_value,
    extract_claims,
    parse_bool,
    parse_number,
)
from src.diagnostics.metrics import compute_accuracy, compute_repeatability
from src.diagnostics.models import (
    AccuracyCheckRow,
    BrandRef,
    FactRef,
    MentionRow,
    ProductRef,
    ResponseRecord,
)
from src.diagnostics.parsing import parse_product_mentions
from src.diagnostics.reference import (
    facts_path,
    load_facts_csv,
    load_products_csv,
    products_path,
)
from tests.test_diagnostics_engine import FakeRepo

SUNSCREEN = ProductRef(
    product_id="SUN-1",
    product_name="Ultra Sheer Sunscreen",
    maker="Neutrogena",
    aliases=["Ultra Sheer"],
    category="sunscreen",
)


def rr(rid: str, prompt: str, text: str, repeat: int = 1) -> ResponseRecord:
    return ResponseRecord(
        response_id=rid,
        run_id="run1",
        prompt_id=prompt,
        provider="perplexity",
        category="c",
        repeat_no=repeat,
        answer_text=text,
        raw_response={"choices": [{"message": {"content": text}}]},
    )


# ---------------------------------------------------------------- products


def test_product_mentions_only_when_present() -> None:
    hit = parse_product_mentions(rr("a", "p", "1. Ultra Sheer SPF 50 is great"), [SUNSCREEN], "v1")
    assert len(hit) == 1 and hit[0].product_id == "SUN-1" and hit[0].rank_in_list == 1
    assert hit[0].extraction_method == "alias_rule" and hit[0].confidence is None
    assert parse_product_mentions(rr("b", "p", "Try a gel sunscreen"), [SUNSCREEN], "v1") == []


def test_diagnose_saves_product_mentions_and_repeatability() -> None:
    repo = FakeRepo()
    repo.products = [ProductRef(product_id="P1", product_name="Nykaa SkinRX", category="serum")]
    out = diagnose(DiagnoseInput(run_id="run1"), repo)
    assert out.n_product_mentions == len(repo.product_mentions)
    assert out.n_repeatability_rows == 0  # engine-test fixture has no repeated prompts


# ---------------------------------------------------------------- repeatability

BRANDS = [BrandRef(brand_id=1, name="Sephora India", aliases=["Sephora"], is_target=True)]


def mention(rid: str, mentioned: bool) -> MentionRow:
    return MentionRow(
        response_id=rid, run_id="run1", brand_id=1, mentioned=mentioned, parser_version="v1"
    )


def test_repeatability_agreement_and_sd() -> None:
    responses = [
        rr("p1a", "P1", "x", 1), rr("p1b", "P1", "x", 2), rr("p1c", "P1", "x", 3),
        rr("p2a", "P2", "x", 1), rr("p2b", "P2", "x", 2),
        rr("p3a", "P3", "x", 1),  # asked once: excluded
    ]  # fmt: skip
    mentions = [
        mention("p1a", True), mention("p1b", True), mention("p1c", True),  # agree
        mention("p2a", True), mention("p2b", False),  # disagree, sd 0.5
        mention("p3a", True),
    ]  # fmt: skip
    (row,) = compute_repeatability("run1", responses, mentions, BRANDS)
    assert row.n_prompts == 2
    assert row.agreement_rate == 0.5
    assert row.mean_within_prompt_sd == pytest.approx(0.25)


def test_repeatability_empty_without_repeats() -> None:
    assert compute_repeatability("run1", [rr("a", "P1", "x")], [mention("a", True)], BRANDS) == []


# ---------------------------------------------------------------- accuracy: compare rules


def fact(value: str, vtype: str, tol: float | None = None, fid: str = "F1") -> FactRef:
    return FactRef(
        fact_id=fid, subject_type="brand", subject="Sephora India", attribute="a",
        approved_value=value, value_type=vtype, tolerance=tol,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("stated", "f", "verdict"),
    [
        (None, fact("true", "boolean"), "not_mentioned"),
        ("  ", fact("50", "number"), "not_mentioned"),
        ("Yes, it offers COD", fact("true", "boolean"), "match"),
        ("not available", fact("true", "boolean"), "mismatch"),
        ("maybe", fact("true", "boolean"), "unverifiable"),
        ("SPF 50+", fact("50", "number"), "match"),
        ("SPF 30", fact("50", "number"), "mismatch"),
        ("₹1,149", fact("1099", "number", 0.10), "match"),
        ("₹1,499", fact("1099", "number", 0.10), "mismatch"),
        ("about a thousand", fact("1099", "number"), "unverifiable"),
        ("Sephora Beauty Pass rewards", fact("Beauty Pass", "text"), "match"),
        ("Nykaa Prive", fact("Beauty Pass", "text"), "mismatch"),
    ],
)
def test_compare_value(stated: str | None, f: FactRef, verdict: str) -> None:
    assert compare_value(stated, f) == verdict


def test_parsers() -> None:
    assert parse_number("Rs. 2,499.50 only") == 2499.5
    assert parse_bool("no") is False and parse_bool("Yes") is True


def test_compute_accuracy_rate_excludes_not_stated() -> None:
    facts = {"F1": fact("true", "boolean")}
    checks = [
        AccuracyCheckRow(response_id=r, run_id="run1", fact_id="F1", stated_value=s,
                         approved_value="true", verdict=v, checker_version="v1")
        for r, s, v in [("a", "yes", "match"), ("b", "no", "mismatch"),
                        ("c", None, "not_mentioned"), ("d", "yes", "match")]
    ]  # fmt: skip
    (row,) = compute_accuracy("run1", checks, facts)
    assert (row.n_checked, row.n_match, row.n_mismatch, row.n_not_mentioned) == (4, 2, 1, 1)
    assert row.accuracy_rate == pytest.approx(2 / 3, abs=1e-4)


# ---------------------------------------------------------------- accuracy: LLM step (mocked)


def test_extract_request_and_fake_client() -> None:
    facts = [fact("true", "boolean", fid="F1"), fact("50", "number", fid="F2")]
    req = build_extract_request(AnalysisConfig(model="m"), "answer", facts, {})
    item_schema = req["text"]["format"]["schema"]["properties"]["claims"]["items"]
    assert item_schema["properties"]["fact_id"]["enum"] == ["F1", "F2"]

    payload = {"claims": [{"fact_id": "F1", "stated_value": "yes"},
                          {"fact_id": "F2", "stated_value": None}]}  # fmt: skip
    raw = {"output": [{"type": "message", "content": [{"type": "output_text",
           "text": json.dumps(payload)}]}]}  # fmt: skip
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kw: SimpleNamespace(model_dump=lambda mode=None: raw)
        )
    )
    out = extract_claims(AnalysisConfig(model="m"), "k", "answer", facts, {}, client=client)
    assert out == {"F1": "yes", "F2": None}


def settings(key: str | None = "k") -> Settings:
    return Settings(project=load_project_config(), openai_api_key=key)


def test_check_accuracy_only_checks_mentioned_subjects() -> None:
    repo = FakeRepo()
    diagnose(DiagnoseInput(run_id="run1"), repo)  # fixture: Sephora in 2 answers, Nykaa in 2
    repo.facts = {
        "F1": FactRef(fact_id="F1", subject_type="brand", subject="Sephora India",
                      attribute="offers_cod", approved_value="true", value_type="boolean"),
        "F2": FactRef(fact_id="F2", subject_type="product", subject="NOT-MENTIONED",
                      attribute="spf", approved_value="50", value_type="number"),
    }  # fmt: skip
    calls = []

    def fake_extract(cfg, key, text, facts, names):
        calls.append([f.fact_id for f in facts])
        return {"F1": "yes"}

    out = check_accuracy(AccuracyInput(run_id="run1"), settings(), repo, extract_fn=fake_extract)
    assert calls and all(ids == ["F1"] for ids in calls)  # product fact never sent
    assert out.n_checks == len(calls) and out.n_failed == 0
    assert all(c.verdict == "match" for c in repo.checks)
    assert repo.gold_accuracy[0].accuracy_rate == 1.0


def test_check_accuracy_needs_facts_and_key() -> None:
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        check_accuracy(AccuracyInput(run_id="run1"), settings(None), FakeRepo())
    with pytest.raises(ValueError, match="No reference facts"):
        check_accuracy(AccuracyInput(run_id="run1"), settings(), FakeRepo())


# ---------------------------------------------------------------- reference files


def test_shipped_catalogue_files_are_valid_and_empty() -> None:
    assert load_products_csv(products_path("v1")) == []
    assert load_facts_csv(facts_path("v1")) == []


def test_products_and_facts_validation(tmp_path: Path) -> None:
    prods = tmp_path / "products.csv"
    prods.write_text(
        "product_id,product_name,maker,aliases,category,source_url,last_verified_at\n"
        "P1,Ultra Sheer,Neutrogena,Ultra Sheer SPF|Dry Touch,sunscreen,https://x,2026-11-23\n",
        encoding="utf-8",
    )
    rows = load_products_csv(prods)
    assert rows[0].aliases == ["Ultra Sheer SPF", "Dry Touch"]

    facts = tmp_path / "facts.csv"
    header = (
        "fact_id,subject_type,subject,attribute,approved_value,value_type,tolerance,"
        "source_url,last_verified_at\n"
    )
    facts.write_text(
        header + "F1,product,P1,spf,50,number,,https://x,2026-11-23\n", encoding="utf-8"
    )
    assert load_facts_csv(facts, {"Sephora India"}, {"P1"})[0].subject == "P1"

    facts.write_text(
        header + "F1,product,P9,spf,50,number,,https://x,2026-11-23\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="unknown product"):
        load_facts_csv(facts, {"Sephora India"}, {"P1"})

    facts.write_text(
        header + "F1,brand,Sephora India,cod,true,boolean,0.1,https://x,2026-11-23\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="tolerance"):
        load_facts_csv(facts)

    facts.write_text(
        header + "F1,brand,Sephora India,cod,true,boolean,,,2026-11-23\n", encoding="utf-8"
    )
    with pytest.raises(ValueError):  # source_url is required
        load_facts_csv(facts)
