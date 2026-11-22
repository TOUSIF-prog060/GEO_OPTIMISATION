"""Phase 0 smoke test: send ONE question to each enabled provider and print the basics.

Usage:  python scripts/smoke_test_providers.py
This makes real, billed API calls (one per provider). Raw JSON is saved to data/raw/smoke/.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import ProviderConfig, get_settings  # noqa: E402

QUESTION = "What is the best sunscreen for oily skin in India under 1000 rupees?"
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
RAW_DIR = ROOT / "data" / "raw" / "smoke"


def ask_perplexity(cfg: ProviderConfig, api_key: str, question: str) -> dict:
    start = time.perf_counter()
    resp = httpx.post(
        PERPLEXITY_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": cfg.model, "messages": [{"role": "user", "content": question}]},
        timeout=cfg.timeout_s,
    )
    latency_ms = int((time.perf_counter() - start) * 1000)
    resp.raise_for_status()
    raw = resp.json()
    citations = raw.get("citations") or [r.get("url") for r in raw.get("search_results", [])]
    usage = raw.get("usage", {})
    return {
        "answer": raw["choices"][0]["message"]["content"],
        "citations": [c for c in citations if c],
        "model": raw.get("model", cfg.model),
        "latency_ms": latency_ms,
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "raw": raw,
    }


def ask_openai(cfg: ProviderConfig, api_key: str, question: str) -> dict:
    client = OpenAI(api_key=api_key, timeout=cfg.timeout_s)
    start = time.perf_counter()
    resp = client.responses.create(model=cfg.model, tools=[{"type": "web_search"}], input=question)
    latency_ms = int((time.perf_counter() - start) * 1000)
    raw = resp.model_dump()
    citations: list[str] = []
    for item in raw.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            for ann in part.get("annotations") or []:
                if ann.get("type") == "url_citation" and ann.get("url") not in citations:
                    citations.append(ann["url"])
    usage = raw.get("usage") or {}
    return {
        "answer": resp.output_text,
        "citations": citations,
        "model": raw.get("model", cfg.model),
        "latency_ms": latency_ms,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "raw": raw,
    }


CALLERS = {
    "perplexity": (ask_perplexity, "perplexity_api_key"),
    "openai": (ask_openai, "openai_api_key"),
}


def main() -> int:
    settings = get_settings()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    print(f"Question: {QUESTION}\n")
    for cfg in settings.project.providers:
        if not cfg.enabled:
            continue
        caller, key_field = CALLERS[cfg.name]
        print(f"== {cfg.name} ({cfg.model}) ==")
        try:
            result = caller(cfg, settings.require(key_field), QUESTION)
        except Exception as exc:
            failures += 1
            print(f"  FAILED: {type(exc).__name__}: {exc}\n")
            continue
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        raw_path = RAW_DIR / f"{cfg.name}_{stamp}.json"
        raw_path.write_text(json.dumps(result["raw"], indent=2, default=str), encoding="utf-8")
        print(f"  model:          {result['model']}")
        print(f"  answer length:  {len(result['answer'])} chars")
        print(f"  citations:      {len(result['citations'])}")
        for url in result["citations"][:5]:
            print(f"    - {url}")
        print(f"  latency:        {result['latency_ms']} ms")
        print(f"  tokens in/out:  {result['input_tokens']} / {result['output_tokens']}")
        print(f"  answer preview: {result['answer'][:200]!r}")
        print(f"  raw saved to:   {raw_path.relative_to(ROOT)}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
