import csv
from pathlib import Path

import pytest

from src.diagnostics.models import BrandRef, MentionRow, ResponseRecord
from src.diagnostics.validation import (
    HumanLabel,
    binary_prf,
    cohen_kappa,
    draw_sample,
    evaluate,
    macro_f1,
    read_sheet,
    write_sheet,
)


def resp(i: int, provider: str, category: str) -> ResponseRecord:
    return ResponseRecord(
        response_id=f"r{i:03d}", run_id="run1", prompt_id=f"P{i}", provider=provider,
        category=category, answer_text="t", raw_response={"x": 1},
    )  # fmt: skip


POOL = (
    [resp(i, "perplexity", "retailer") for i in range(60)]
    + [resp(i, "openai", "retailer") for i in range(60, 90)]
    + [resp(i, "openai", "sunscreen") for i in range(90, 100)]
)


def test_sample_is_stratified_seeded_and_sized() -> None:
    s1 = draw_sample(POOL, 20, seed=1)
    s2 = draw_sample(POOL, 20, seed=1)
    assert len(s1) == 20 and [r.response_id for r in s1] == [r.response_id for r in s2]
    strata = {(r.provider, r.category) for r in s1}
    assert len(strata) == 3  # every stratum represented
    assert sum(r.provider == "perplexity" for r in s1) == 12  # proportional: 60%


def test_sample_skips_errors_and_caps_at_pool() -> None:
    bad = ResponseRecord(response_id="x", run_id="r", prompt_id="p", provider="o",
                         category="c", error="boom")  # fmt: skip
    assert draw_sample([bad, *POOL[:3]], 50) == sorted(POOL[:3], key=lambda r: r.response_id)


def test_binary_prf() -> None:
    res = binary_prf([True, True, False, False], [True, False, True, False])
    assert (res.precision, res.recall, res.f1, res.support) == (0.5, 0.5, 0.5, 2)
    perfect = binary_prf([True, False], [True, False])
    assert perfect.f1 == 1.0
    assert binary_prf([True], [False]).f1 == 0.0


def test_kappa_and_macro_f1() -> None:
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0
    assert cohen_kappa([], []) is None
    assert macro_f1(["pos", "neg"], ["pos", "neg"]) == 1.0


def test_sheet_round_trip(tmp_path: Path) -> None:
    brands = [BrandRef(brand_id=1, name="Nykaa", aliases=["Nykaa"])]
    path = tmp_path / "sheet.csv"
    assert write_sheet(path, "s1", POOL[:2], brands) == 2

    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rows[0].update(mentioned="Yes", rank_in_list="2", sentiment="Positive", is_recommended="no")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)  # second row left blank = not labelled yet

    labels = read_sheet(path, "TS")
    assert len(labels) == 1
    lab = labels[0]
    assert lab.mentioned is True and lab.rank_in_list == 2
    assert lab.sentiment == "positive" and lab.is_recommended is False and lab.labeller == "TS"


def test_sheet_rejects_bad_value(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "sample_version,response_id,brand,prompt_text,answer_text,mentioned,rank_in_list,"
        "sentiment,is_recommended,notes\ns1,r1,Nykaa,q,a,perhaps,,,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line 2"):
        read_sheet(path, "TS")


def lab(rid: str, who: str, mentioned: bool, sentiment: str | None = None) -> HumanLabel:
    return HumanLabel(sample_version="s1", response_id=rid, brand="Nykaa", labeller=who,
                      mentioned=mentioned, sentiment=sentiment)  # fmt: skip


def sysm(rid: str, mentioned: bool, sentiment: str | None = None) -> MentionRow:
    return MentionRow(response_id=rid, run_id="run1", brand_id=1, mentioned=mentioned,
                      sentiment=sentiment, parser_version="v1")  # fmt: skip


def test_evaluate_consensus_metrics_and_errors() -> None:
    labels = [
        lab("r1", "A", True, "positive"), lab("r1", "B", True, "positive"),
        lab("r2", "A", False), lab("r2", "B", False),
        lab("r3", "A", True), lab("r3", "B", True),
        lab("r4", "A", True), lab("r4", "B", False),  # disagreement -> excluded
        lab("r5", "A", False),  # only one labeller -> excluded
    ]  # fmt: skip
    system = [sysm("r1", True, "positive"), sysm("r2", True), sysm("r3", False), sysm("r4", True)]
    rep = evaluate("s1", labels, system, {"Nykaa": 1})

    assert rep.labellers == ["A", "B"] and rep.n_items == 4 and rep.n_disagreements == 1
    # reference: r1 T, r2 F, r3 T ; system: r1 T, r2 T, r3 F
    assert rep.mentioned.precision == 0.5 and rep.mentioned.recall == 0.5
    assert rep.sentiment_accuracy == 1.0 and rep.sentiment_n == 1
    assert {e["response_id"] for e in rep.errors} == {"r2", "r3"}
    assert rep.kappa_mentioned is not None
