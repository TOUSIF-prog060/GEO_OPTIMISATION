"""Accuracy checks: does an AI answer state brand/product facts correctly?

Two steps, kept separate so each can be evaluated:
  1. extract (LLM): what value does the answer state for each relevant fact? (or null)
  2. compare (rules, checker v1): stated vs approved value -> match | mismatch |
     not_mentioned | unverifiable
Only facts whose subject (brand or product) is mentioned in the answer are checked.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.config import AnalysisConfig
from src.diagnostics.models import FactRef, Verdict
from src.discovery.providers import parse_openai

CHECKER_VERSION = "v1"
MAX_ANSWER_CHARS = 6000

TRUE_WORDS = {"true", "yes", "available", "offers", "offered", "supported", "y"}
FALSE_WORDS = {"false", "no", "not", "unavailable", "none", "n"}
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_WORD = re.compile(r"[a-z0-9]+")

EXTRACT_INSTRUCTIONS = (
    "You extract factual claims from an AI shopping assistant's answer. "
    "For each requested fact (a subject and an attribute), return the value the ANSWER "
    "states, copied or briefly normalised (e.g. '50', 'true', '₹1,099'). "
    "Return null if the answer does not state it. Never use outside knowledge "
    "and never guess."
)


# ---------------------------------------------------------------- step 1: extract (LLM)


def build_extract_request(
    cfg: AnalysisConfig, answer_text: str, facts: list[FactRef], subject_names: dict[str, str]
) -> dict[str, Any]:
    wanted = "\n".join(
        f"- fact_id={f.fact_id}: {subject_names.get(f.subject, f.subject)} → {f.attribute} "
        f"({f.value_type})"
        for f in facts
    )
    schema = {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "fact_id": {"type": "string", "enum": [f.fact_id for f in facts]},
                        "stated_value": {"type": ["string", "null"]},
                    },
                    "required": ["fact_id", "stated_value"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["claims"],
        "additionalProperties": False,
    }
    return {
        "model": cfg.model,
        "instructions": EXTRACT_INSTRUCTIONS,
        "input": f"Facts to extract:\n{wanted}\n\nAI answer:\n{answer_text[:MAX_ANSWER_CHARS]}",
        "text": {
            "format": {"type": "json_schema", "name": "claims", "schema": schema, "strict": True}
        },
    }


def parse_extraction(raw: dict[str, Any]) -> dict[str, str | None]:
    text = parse_openai(raw)[0]
    if not text:
        raise ValueError("empty extraction response")
    data = json.loads(text)
    return {c["fact_id"]: c.get("stated_value") for c in data.get("claims", [])}


def extract_claims(
    cfg: AnalysisConfig,
    api_key: str,
    answer_text: str,
    facts: list[FactRef],
    subject_names: dict[str, str],
    client: Any | None = None,
) -> dict[str, str | None]:
    from openai import OpenAI  # lazy: tests and dry runs need no SDK client

    sdk = client or OpenAI(api_key=api_key, timeout=cfg.timeout_s)
    resp = sdk.responses.create(**build_extract_request(cfg, answer_text, facts, subject_names))
    return parse_extraction(resp.model_dump(mode="json"))


# ---------------------------------------------------------------- step 2: compare (rules)


def parse_bool(value: str) -> bool | None:
    words = set(_WORD.findall(value.lower()))
    t, f = bool(words & TRUE_WORDS), bool(words & FALSE_WORDS)
    if t == f:  # neither, or contradictory ("not available")
        return False if {"not", "available"} <= words else None
    return t


def parse_number(value: str) -> float | None:
    m = _NUMBER.search(value)
    return float(m.group().replace(",", "")) if m else None


def compare_value(stated: str | None, fact: FactRef) -> Verdict:
    if stated is None or not stated.strip():
        return "not_mentioned"
    if fact.value_type == "boolean":
        s, a = parse_bool(stated), parse_bool(fact.approved_value)
        if s is None or a is None:
            return "unverifiable"
        return "match" if s == a else "mismatch"
    if fact.value_type == "number":
        s, a = parse_number(stated), parse_number(fact.approved_value)
        if s is None or a is None:
            return "unverifiable"
        tol = fact.tolerance or 0.0
        ok = abs(s - a) <= tol * abs(a) if a else s == a
        return "match" if ok else "mismatch"
    # text: every word of the approved value must appear in the stated value
    approved = set(_WORD.findall(fact.approved_value.lower()))
    stated_words = set(_WORD.findall(stated.lower()))
    if not approved:
        return "unverifiable"
    return "match" if approved <= stated_words else "mismatch"
