"""Optional LLM step: label each brand mention with sentiment and is_recommended.

Uses the analysis model from the config (OpenAI Responses API, structured JSON output).
The key is passed in by the caller; tests inject a fake client.
"""

from __future__ import annotations

import json
from typing import Any

from src.config import AnalysisConfig
from src.diagnostics.models import MentionLabel, MentionToLabel
from src.discovery.providers import parse_openai

MAX_ANSWER_CHARS = 6000

INSTRUCTIONS = (
    "You label how an AI shopping assistant's answer treats ONE brand. "
    "Judge only what the answer text says about that brand; do not use outside knowledge.\n"
    "sentiment: positive | neutral | negative | mixed (tone toward the brand).\n"
    "is_recommended: true only if the answer suggests the user buy from / use this brand "
    "(e.g. lists it as a good option); false if it is only named, compared neutrally, "
    "or advised against."
)

LABEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative", "mixed"]},
        "is_recommended": {"type": "boolean"},
    },
    "required": ["sentiment", "is_recommended"],
    "additionalProperties": False,
}


def build_label_request(cfg: AnalysisConfig, item: MentionToLabel) -> dict[str, Any]:
    user = (
        f"Brand: {item.brand_name}\n\n"
        f"User question: {item.prompt_text}\n\n"
        f"AI answer:\n{item.answer_text[:MAX_ANSWER_CHARS]}"
    )
    return {
        "model": cfg.model,
        "instructions": INSTRUCTIONS,
        "input": user,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "mention_label",
                "schema": LABEL_SCHEMA,
                "strict": True,
            }
        },
    }


def parse_label(raw: dict[str, Any]) -> MentionLabel:
    text = parse_openai(raw)[0]
    if not text:
        raise ValueError("empty label response")
    return MentionLabel.model_validate(json.loads(text))


def label_mention(
    cfg: AnalysisConfig, api_key: str, item: MentionToLabel, client: Any | None = None
) -> MentionLabel:
    from openai import OpenAI  # lazy: dry runs and tests need no SDK client

    sdk = client or OpenAI(api_key=api_key, timeout=cfg.timeout_s)
    resp = sdk.responses.create(**build_label_request(cfg, item))
    return parse_label(resp.model_dump(mode="json"))
