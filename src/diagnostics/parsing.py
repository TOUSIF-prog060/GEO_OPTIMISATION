"""Turn one raw Bronze response into Silver rows: citations and brand mentions.

Deterministic and rule-based (no LLM), so re-running gives the same result.
Bump PARSER_VERSION whenever these rules change.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from src.diagnostics.models import (
    BrandRef,
    CitationRow,
    DomainRef,
    MentionRow,
    ProductMentionRow,
    ProductRef,
    ResponseRecord,
)
from src.discovery.providers import gemini_citations, parse_openai, parse_perplexity

PARSER_VERSION = "v1"
SNIPPET_WIDTH = 80

CITATION_PARSERS = {
    "perplexity": parse_perplexity,
    "openai": parse_openai,
    "gemini": gemini_citations,
}

# A list item: "1. ", "2) ", "- ", "* ", "• " or a markdown heading "### ", at the start of a line.
_LIST_ITEM = re.compile(r"^(?P<indent>[ \t]*)(?:\d{1,2}[.)]|[-*•]|#{1,6})\s+(?P<body>.+)$")


# ---------------------------------------------------------------- domains


def normalise_domain(url: str) -> str | None:
    """'https://www.Nykaa.com/x?y' -> 'nykaa.com'. None if the URL has no host."""
    try:
        host = urlparse(url.strip()).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower().rstrip(".")
    for prefix in ("www.", "m.", "amp."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host or None


def classify_domain(domain: str, domains: dict[str, DomainRef]) -> DomainRef | None:
    """Exact match, else the closest parent domain ('blog.nykaa.com' -> 'nykaa.com')."""
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        ref = domains.get(".".join(parts[i:]))
        if ref:
            return ref
    return None


# ---------------------------------------------------------------- citations


def extract_citation_urls(provider: str, raw: dict[str, Any]) -> list[str]:
    parser = CITATION_PARSERS.get(provider)
    return parser(raw)[1] if parser else []


def parse_citations(resp: ResponseRecord, parser_version: str) -> list[CitationRow]:
    rows: list[CitationRow] = []
    for url in extract_citation_urls(resp.provider, resp.raw_response or {}):
        domain = normalise_domain(url)
        if not domain:
            continue
        rows.append(
            CitationRow(
                response_id=resp.response_id,
                run_id=resp.run_id,
                position=len(rows) + 1,
                url=url,
                domain=domain,
                parser_version=parser_version,
            )
        )
    return rows


# ---------------------------------------------------------------- mentions


def alias_pattern(aliases: list[str]) -> re.Pattern[str]:
    """Case-insensitive, whole-word match on any alias; longest alias wins on overlap."""
    alts = sorted({a.strip() for a in aliases if a.strip()}, key=len, reverse=True)
    body = "|".join(re.escape(a) for a in alts)
    return re.compile(rf"(?<![\w])(?:{body})(?![\w])", re.IGNORECASE)


def find_mentions(text: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in pattern.finditer(text)]


def list_items(text: str) -> list[str]:
    """Top-level list items / headings, in order. Nested (indented) items are skipped."""
    items: list[str] = []
    for line in text.splitlines():
        m = _LIST_ITEM.match(line)
        if m and len(m.group("indent").expandtabs(4)) < 2:
            items.append(m.group("body"))
    return items


def rank_in_list(items: list[str], pattern: re.Pattern[str]) -> int | None:
    """1-based position of the first list item naming the brand, or None."""
    for i, item in enumerate(items, start=1):
        if pattern.search(item):
            return i
    return None


def make_snippet(text: str, start: int, end: int, width: int = SNIPPET_WIDTH) -> str:
    a, b = max(0, start - width), min(len(text), end + width)
    return (
        ("…" if a else "") + text[a:b].replace("\n", " ").strip() + ("…" if b < len(text) else "")
    )


def parse_mentions(
    resp: ResponseRecord, brands: list[BrandRef], parser_version: str
) -> list[MentionRow]:
    """One row per brand per response, including brands that were NOT mentioned."""
    text = resp.answer_text or ""
    items = list_items(text)
    rows: list[MentionRow] = []
    for brand in brands:
        pattern = alias_pattern(brand.aliases + [brand.name])
        hits = find_mentions(text, pattern)
        first = hits[0] if hits else None
        rows.append(
            MentionRow(
                response_id=resp.response_id,
                run_id=resp.run_id,
                brand_id=brand.brand_id,
                mentioned=bool(hits),
                mention_count=len(hits),
                first_char_pos=first[0] if first else None,
                rank_in_list=rank_in_list(items, pattern) if hits else None,
                snippet=make_snippet(text, *first) if first else None,
                parser_version=parser_version,
            )
        )
    return rows


def parse_product_mentions(
    resp: ResponseRecord, products: list[ProductRef], parser_version: str
) -> list[ProductMentionRow]:
    """Rows only for products that ARE mentioned (the catalogue can be large)."""
    text = resp.answer_text or ""
    items = list_items(text)
    rows: list[ProductMentionRow] = []
    for prod in products:
        pattern = alias_pattern(prod.aliases + [prod.product_name])
        hits = find_mentions(text, pattern)
        if not hits:
            continue
        rows.append(
            ProductMentionRow(
                response_id=resp.response_id,
                run_id=resp.run_id,
                product_id=prod.product_id,
                mention_count=len(hits),
                first_char_pos=hits[0][0],
                rank_in_list=rank_in_list(items, pattern),
                snippet=make_snippet(text, *hits[0]),
                parser_version=parser_version,
            )
        )
    return rows


def parse_response(
    resp: ResponseRecord, brands: list[BrandRef], parser_version: str = PARSER_VERSION
) -> tuple[list[CitationRow], list[MentionRow]]:
    return parse_citations(resp, parser_version), parse_mentions(resp, brands, parser_version)
