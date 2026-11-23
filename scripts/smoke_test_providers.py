"""Phase 0 smoke test: send ONE question to each enabled provider and print the basics.

Usage:  python scripts/smoke_test_providers.py
This makes real, billed API calls (one per provider). Raw JSON is saved to data/raw/smoke/.
Uses the same client functions as the discovery engine (src/discovery/providers.py).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402
from src.discovery.providers import get_api_key, get_ask_fn, key_field  # noqa: E402

QUESTION = "What is the best sunscreen for oily skin in India under 1000 rupees?"
RAW_DIR = ROOT / "data" / "raw" / "smoke"


def main() -> int:
    settings = get_settings()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    print(f"Question: {QUESTION}\n")
    for cfg in settings.project.providers:
        if not cfg.enabled:
            continue
        print(f"== {cfg.name} ({cfg.model}) ==")
        api_key = get_api_key(settings, cfg.name)
        if not api_key:
            failures += 1
            print(f"  SKIPPED: {key_field(cfg.name).upper()} is not set in .env\n")
            continue
        try:
            result = get_ask_fn(cfg.name)(cfg, api_key, QUESTION)
        except Exception as exc:
            failures += 1
            print(f"  FAILED: {type(exc).__name__}: {exc}\n")
            continue
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        raw_path = RAW_DIR / f"{cfg.name}_{stamp}.json"
        raw_path.write_text(json.dumps(result.raw, indent=2, default=str), encoding="utf-8")
        print(f"  model:          {result.model}")
        print(f"  answer length:  {len(result.answer_text)} chars")
        print(f"  citations:      {len(result.citations)}")
        for url in result.citations[:5]:
            print(f"    - {url}")
        print(f"  latency:        {result.latency_ms} ms")
        print(f"  tokens in/out:  {result.input_tokens} / {result.output_tokens}")
        cost = result.cost_usd if result.cost_usd is not None else "prices not set"
        print(f"  cost (est.):    {cost}")
        print(f"  answer preview: {result.answer_text[:200]!r}")
        print(f"  raw saved to:   {raw_path.relative_to(ROOT)}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
