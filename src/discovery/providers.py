"""Provider clients: send one question to an AI answer engine and return its raw answer.

Keys are passed in by the caller (read from .env via src.config). Nothing here reads
environment variables directly, which keeps these functions easy to test with mocks.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from src.config import ProviderConfig, Settings
from src.discovery.models import ProviderAnswer

logger = logging.getLogger(__name__)

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"

AskFn = Callable[[ProviderConfig, str, str], ProviderAnswer]


def estimate_cost(
    cfg: ProviderConfig, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    """USD cost from the per-token / per-request prices in the config. None if prices unset."""
    prices = (cfg.price_input_per_mtok, cfg.price_output_per_mtok, cfg.price_per_request)
    if all(p is None for p in prices):
        return None
    cost = cfg.price_per_request or 0.0
    cost += (input_tokens or 0) / 1_000_000 * (cfg.price_input_per_mtok or 0.0)
    cost += (output_tokens or 0) / 1_000_000 * (cfg.price_output_per_mtok or 0.0)
    return round(cost, 6)


# ---------------------------------------------------------------- Perplexity


def build_perplexity_request(cfg: ProviderConfig, question: str) -> dict[str, Any]:
    return {"model": cfg.model, "messages": [{"role": "user", "content": question}]}


def parse_perplexity(raw: dict[str, Any]) -> tuple[str, list[str], int | None, int | None]:
    """Return (answer_text, citations, input_tokens, output_tokens) from a Sonar payload."""
    answer = raw["choices"][0]["message"]["content"]
    urls = raw.get("citations") or [r.get("url") for r in raw.get("search_results") or []]
    citations = _dedupe([u for u in urls if u])
    usage = raw.get("usage") or {}
    return answer, citations, usage.get("prompt_tokens"), usage.get("completion_tokens")


def ask_perplexity(
    cfg: ProviderConfig, api_key: str, question: str, client: httpx.Client | None = None
) -> ProviderAnswer:
    payload = build_perplexity_request(cfg, question)
    http = client or httpx.Client(timeout=cfg.timeout_s)
    try:
        start = time.perf_counter()
        resp = http.post(
            PERPLEXITY_URL, headers={"Authorization": f"Bearer {api_key}"}, json=payload
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        resp.raise_for_status()
        raw = resp.json()
    finally:
        if client is None:
            http.close()
    answer, citations, tin, tout = parse_perplexity(raw)
    return ProviderAnswer(
        answer_text=answer,
        citations=citations,
        model=raw.get("model", cfg.model),
        request=payload,
        raw=raw,
        latency_ms=latency_ms,
        input_tokens=tin,
        output_tokens=tout,
        cost_usd=estimate_cost(cfg, tin, tout),
        http_status=resp.status_code,
    )


# ---------------------------------------------------------------- OpenAI (Responses + web_search)


def build_openai_request(cfg: ProviderConfig, question: str) -> dict[str, Any]:
    return {"model": cfg.model, "tools": [{"type": "web_search"}], "input": question}


def parse_openai(raw: dict[str, Any]) -> tuple[str, list[str], int | None, int | None]:
    """Return (answer_text, citations, input_tokens, output_tokens) from a Responses payload."""
    texts: list[str] = []
    urls: list[str] = []
    for item in raw.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text":
                texts.append(part.get("text", ""))
            for ann in part.get("annotations") or []:
                if ann.get("type") == "url_citation" and ann.get("url"):
                    urls.append(ann["url"])
    usage = raw.get("usage") or {}
    return "".join(texts), _dedupe(urls), usage.get("input_tokens"), usage.get("output_tokens")


def ask_openai(
    cfg: ProviderConfig, api_key: str, question: str, client: Any | None = None
) -> ProviderAnswer:
    from openai import OpenAI  # imported lazily so tests and dry runs need no client

    payload = build_openai_request(cfg, question)
    sdk = client or OpenAI(api_key=api_key, timeout=cfg.timeout_s)
    start = time.perf_counter()
    resp = sdk.responses.create(**payload)
    latency_ms = int((time.perf_counter() - start) * 1000)
    raw = resp.model_dump(mode="json")
    answer, citations, tin, tout = parse_openai(raw)
    return ProviderAnswer(
        answer_text=answer,
        citations=citations,
        model=raw.get("model", cfg.model),
        request=payload,
        raw=raw,
        latency_ms=latency_ms,
        input_tokens=tin,
        output_tokens=tout,
        cost_usd=estimate_cost(cfg, tin, tout),
    )


# ---------------------------------------------------------------- registry

PROVIDERS: dict[str, AskFn] = {
    "perplexity": ask_perplexity,
    "openai": ask_openai,
}


def key_field(provider: str) -> str:
    """Settings attribute holding this provider's API key, e.g. 'openai_api_key'."""
    return f"{provider}_api_key"


def get_api_key(settings: Settings, provider: str) -> str | None:
    return getattr(settings, key_field(provider), None)


def get_ask_fn(provider: str) -> AskFn:
    try:
        return PROVIDERS[provider]
    except KeyError as exc:
        raise KeyError(f"No client for provider '{provider}'. Known: {sorted(PROVIDERS)}") from exc


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
