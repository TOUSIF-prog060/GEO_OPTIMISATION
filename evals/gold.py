"""Gold sets for the sandbox evaluation (version gold_v1).

These are SYNTHETIC test answers written to probe the rules. Their expected values are true by
construction (we wrote the text), so they measure the parser, not the AI engines. Several cases
copy the formatting seen in real Gemini answers (bold bullets, intro headings, comparison
sections) because that is where rule-based extraction is most likely to go wrong.

Labelling definitions (what a careful human would record):
- mentioned: the brand is named by any of its names or its domain, whatever the sentiment
  ("not on Nykaa" still names Nykaa). Words that merely contain a name ("tiramisu") do not count.
- rank: 1-based position of the brand among the options the answer recommends or ranks.
  None when the brand is named but the answer does not rank it (prose, comparison sections,
  a passing reference inside another option's description).
"""

from __future__ import annotations

from dataclasses import dataclass, field

GOLD_VERSION = "gold_v1"

S, N, T = "Sephora India", "Nykaa", "Tira"
NOT_RANKED = 0  # brand is mentioned, but not ranked


@dataclass(frozen=True)
class MentionCase:
    case_id: str
    tag: str  # what the case probes
    text: str
    expect: dict[str, int] = field(default_factory=dict)  # brand -> rank (0 = not ranked)


MENTION_CASES: list[MentionCase] = [
    MentionCase("M01", "numbered_list",
                "Here are the best places:\n1. Nykaa – huge range\n2. Sephora India – luxury\n"
                "3. Tira – newer", {N: 1, S: 2, T: 3}),
    MentionCase("M02", "bold_bullets",
                "Top picks:\n*   **Nykaa**: wide range.\n*   **Tira**: Reliance-backed.\n"
                "*   **Sephora India**: premium brands.", {N: 1, T: 2, S: 3}),
    MentionCase("M03", "heading_then_list",
                "### Top online stores\n1. **Tira** – good offers\n2. **Nykaa** – fast delivery",
                {T: 1, N: 2}),
    MentionCase("M04", "intro_heading_bullets",
                "## Where to buy\nHere are options:\n*   **Nykaa** has the widest range.\n"
                "*   **Sephora India** stocks prestige brands.", {N: 1, S: 2}),
    MentionCase("M05", "paren_numbers", "1) Sephora India\n2) Nykaa", {S: 1, N: 2}),
    MentionCase("M06", "numbered_headings",
                "## 1. Nykaa\nGreat sales.\n## 2. Sephora India\nCurated luxury.", {N: 1, S: 2}),
    MentionCase("M07", "bold_numbers",
                "**1. Nykaa** – best overall\n**2. Tira** – best app", {N: 1, T: 2}),
    MentionCase("M08", "markdown_table",
                "| Rank | Store |\n|---|---|\n| 1 | Tira |\n| 2 | Nykaa |", {T: 1, N: 2}),
    MentionCase("M09", "brand_twice_in_list",
                "1. Nykaa\n2. Purplle (often cheaper than Nykaa)\n3. Sephora India", {N: 1, S: 3}),
    MentionCase("M10", "passing_reference_in_list",
                "1. Purplle – often beats Nykaa on price\n2. Tira – good loyalty points",
                {N: NOT_RANKED, T: 2}),
    MentionCase("M11", "comparison_sections",
                "**Nykaa**\n*   **Range:** Nykaa has more brands.\n*   **Price:** frequent sales.\n"
                "**Sephora India**\n*   **Range:** Sephora India focuses on prestige.\n"
                "**Tira**\n*   **Range:** Tira is growing fast.",
                {N: NOT_RANKED, S: NOT_RANKED, T: NOT_RANKED}),
    MentionCase("M12", "choose_if_bullets",
                "Both are good.\n*   Choose **Tira** if you want exclusive launches.\n"
                "*   Choose **Sephora India** if you prefer its Beauty Pass.",
                {T: NOT_RANKED, S: NOT_RANKED}),
    MentionCase("M13", "prose_only", "You can buy from Nykaa or Sephora India; both are authentic.",
                {N: NOT_RANKED, S: NOT_RANKED}),
    MentionCase("M14", "negation", "Tira does not stock this brand; buy it on Nykaa instead.",
                {T: NOT_RANKED, N: NOT_RANKED}),
    MentionCase("M15", "substring_tiramisu", "Try the tiramisu lip balm from a local chemist.", {}),
    MentionCase("M16", "substring_tirade", "There was a tirade online about fake perfumes.", {}),
    MentionCase("M17", "substring_city", "The parcel ships from Tirana within a week.", {}),
    MentionCase("M18", "domains", "Check sephora.in and nykaa.com for current offers.",
                {S: NOT_RANKED, N: NOT_RANKED}),
    MentionCase("M19", "possessive", "Nykaa's Pink Friday sale has the deepest discounts.",
                {N: NOT_RANKED}),
    MentionCase("M20", "short_alias", "Sephora carries Fenty Beauty in India.", {S: NOT_RANKED}),
    MentionCase("M21", "sub_brand", "Nykaa Fashion also sells accessories.", {N: NOT_RANKED}),
    MentionCase("M22", "lowercase", "i usually order from nykaa because delivery is quick",
                {N: NOT_RANKED}),
    MentionCase("M23", "uppercase", "TIRA BEAUTY has stores in Mumbai.", {T: NOT_RANKED}),
    MentionCase("M24", "hyphenated", "Look for Sephora-exclusive brands like Rare Beauty.",
                {S: NOT_RANKED}),
    MentionCase("M25", "no_brands", "Buy directly from brand websites such as Lakme or Maybelline.",
                {}),
    MentionCase("M26", "empty_answer", "", {}),
    MentionCase("M27", "all_prose", "Sephora India and Nykaa are both reliable; Tira is newer.",
                {S: NOT_RANKED, N: NOT_RANKED, T: NOT_RANKED}),
    MentionCase("M28", "nested_list",
                "1. Big multi-brand stores\n   - Purplle\n   - Myntra\n2. Nykaa\n3. Tira",
                {N: 2, T: 3}),
    MentionCase("M29", "rank_after_long_intro",
                "Authenticity matters when buying online.\n\nPrices vary by season.\n\n"
                "Best options:\n- Sephora India\n- Tira\n- Nykaa", {S: 1, T: 2, N: 3}),
    MentionCase("M30", "competitor_luxe", "Nykaa Luxe is the premium arm of the store.",
                {N: NOT_RANKED}),
]  # fmt: skip


@dataclass(frozen=True)
class UrlCase:
    url: str
    domain: str | None  # expected normalised domain
    owner: str | None = None  # expected owning brand via the domain reference list


URL_CASES: list[UrlCase] = [
    UrlCase("https://www.Nykaa.com/x?y=1", "nykaa.com", N),
    UrlCase("https://m.tirabeauty.com/p/123", "tirabeauty.com", T),
    UrlCase("http://amp.sephora.in/brand", "sephora.in", S),
    UrlCase("https://blog.nykaa.com/article", "blog.nykaa.com", N),
    UrlCase("https://purplle.com./serum", "purplle.com", None),
    UrlCase("https://www.amazon.in/dp/B0", "amazon.in", None),
    UrlCase("not a url", None, None),
    UrlCase("https://reddit.com/r/IndianSkincareAddicts", "reddit.com", None),
    UrlCase("https://sephora.com/us", "sephora.com", None),  # global site, not Sephora India
    UrlCase("https://WWW.TIRABEAUTY.COM", "tirabeauty.com", T),
]
