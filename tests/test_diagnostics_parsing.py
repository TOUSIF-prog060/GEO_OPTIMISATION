import pytest

from src.diagnostics.models import BrandRef, DomainRef, ResponseRecord
from src.diagnostics.parsing import (
    alias_pattern,
    classify_domain,
    list_items,
    normalise_domain,
    parse_response,
    rank_in_list,
)

BRANDS = [
    BrandRef(
        brand_id=1,
        name="Sephora India",
        aliases=["Sephora", "Sephora India", "sephora.in"],
        is_target=True,
    ),
    BrandRef(brand_id=2, name="Nykaa", aliases=["Nykaa", "Nykaa Fashion", "nykaa.com"]),
    BrandRef(brand_id=3, name="Tira", aliases=["Tira", "Tira Beauty", "tirabeauty.com"]),
]

ANSWER = """Here are the best places to buy makeup online in India:

1. **Nykaa** – huge range and frequent sales. Nykaa also runs offline stores.
2. **Sephora India** – best for luxury brands.
   - sub point mentioning Tira should not count as a top-level item
3. Amazon India – convenient delivery.

I'd skip anything that sounds like tiramisu."""


def resp(
    provider: str = "perplexity", raw: dict | None = None, text: str = ANSWER
) -> ResponseRecord:
    return ResponseRecord(
        response_id="r1",
        run_id="run1",
        prompt_id="RET-001",
        provider=provider,
        category="retailer",
        answer_text=text,
        raw_response=raw if raw is not None else {"choices": [{"message": {"content": text}}]},
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.Nykaa.com/lipstick?x=1", "nykaa.com"),
        ("https://m.sephora.in/", "sephora.in"),
        ("http://blog.tirabeauty.com/a", "blog.tirabeauty.com"),
        ("not a url", None),
    ],
)
def test_normalise_domain(url: str, expected: str | None) -> None:
    assert normalise_domain(url) == expected


def test_classify_domain_uses_parent() -> None:
    refs = {"nykaa.com": DomainRef(domain="nykaa.com", domain_type="competitor", brand_id=2)}
    assert classify_domain("blog.nykaa.com", refs).brand_id == 2
    assert classify_domain("nykaa.com", refs).brand_id == 2
    assert classify_domain("amazon.in", refs) is None


def test_alias_whole_word_and_case() -> None:
    p = alias_pattern(["Tira"])
    assert p.search("buy on TIRA today")
    assert not p.search("tiramisu")
    assert not p.search("satiraj")


def test_longest_alias_counts_once() -> None:
    p = alias_pattern(["Sephora", "Sephora India"])
    assert len(p.findall("Sephora India is great")) == 1


def test_list_items_skip_nested() -> None:
    items = list_items(ANSWER)
    assert len(items) == 3
    assert items[0].startswith("**Nykaa**")


def test_rank_in_list() -> None:
    items = list_items(ANSWER)
    assert rank_in_list(items, alias_pattern(["Sephora India"])) == 2
    assert rank_in_list(items, alias_pattern(["Tira"])) is None  # only in a nested bullet


def test_parse_mentions_one_row_per_brand() -> None:
    _, mentions = parse_response(resp(), BRANDS)
    by_id = {m.brand_id: m for m in mentions}
    assert len(mentions) == 3
    assert by_id[2].mentioned and by_id[2].mention_count == 2 and by_id[2].rank_in_list == 1
    assert by_id[1].mentioned and by_id[1].rank_in_list == 2
    assert by_id[3].mentioned and by_id[3].rank_in_list is None
    assert "Nykaa" in by_id[2].snippet
    assert all(m.parser_version == "v1" and m.run_id == "run1" for m in mentions)


def test_not_mentioned_brand_has_empty_facts() -> None:
    _, mentions = parse_response(resp(text="Try Purplle."), BRANDS)
    assert not any(m.mentioned for m in mentions)
    assert all(m.snippet is None and m.first_char_pos is None for m in mentions)


def test_parse_citations_perplexity_and_openai() -> None:
    pplx = {
        "choices": [{"message": {"content": "x"}}],
        "citations": ["https://www.nykaa.com/a", "bad"],
    }
    cites, _ = parse_response(resp(raw=pplx), BRANDS)
    assert [(c.position, c.domain) for c in cites] == [(1, "nykaa.com")]

    oa = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "x",
          "annotations": [{"type": "url_citation", "url": "https://sephora.in/p"}]}]}]}  # fmt: skip
    cites, _ = parse_response(resp("openai", raw=oa), BRANDS)
    assert cites[0].domain == "sephora.in" and cites[0].response_id == "r1"


def test_gemini_citations_use_source_domains() -> None:
    from src.diagnostics.parsing import extract_citation_urls

    raw = {
        "candidates": [
            {
                "content": {"parts": [{"text": "x"}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {"web": {"uri": "https://vertexaisearch.cloud.google.com/r/1",
                                 "title": "purplle.com"}},  # fmt: skip
                    ]
                },
            }
        ]
    }
    assert extract_citation_urls("gemini", raw) == ["https://purplle.com"]
