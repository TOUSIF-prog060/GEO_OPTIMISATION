"""Live model check (opt-in, billed against the provider's quota).

Asks a few panel questions several times on one engine and measures, in memory only (nothing is
written to the database): reliability, latency, how stable the brand mentions, list positions
and cited sources are across repeats, and how often the target brand appears.

There is no ground truth for "the right answer" here, so this measures consistency and
behaviour, not correctness. Correctness of facts needs verified reference facts (see
data/reference/reference_facts_v1.csv) and human labels (see the Check accuracy page).
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from itertools import combinations
from statistics import mean, median
from typing import Any

from evals.suites import brands, response
from src.config import get_settings
from src.diagnostics.parsing import normalise_domain, parse_mentions
from src.discovery.panel import load_panel, panel_path
from src.discovery.providers import get_api_key, get_ask_fn

DEFAULT_PROMPTS = ["RET-001", "SER-001", "CMP-001"]
MIN_PROMPTS_FOR_STABILITY = 2  # prompts with >= 2 successful repeats needed to report stability


def _jaccard(a: set[str], b: set[str]) -> float | None:
    return len(a & b) / len(a | b) if a | b else None


def eval_live(provider: str = "gemini", prompt_ids: list[str] | None = None, repeats: int = 3,
              pause_s: float = 7.0) -> dict[str, Any]:  # fmt: skip
    settings = get_settings()
    key = get_api_key(settings, provider)
    if not key:
        return {"skipped": f"No API key for {provider}", "metrics": {}, "failures": []}
    cfg = settings.project.provider(provider)
    ask = get_ask_fn(provider)
    wanted = prompt_ids or DEFAULT_PROMPTS
    prompts = [p for p in load_panel(panel_path("v0")) if p.prompt_id in wanted]
    bs = brands()
    names = {b.brand_id: b.name for b in bs}
    target = next(b.name for b in bs if b.is_target)

    calls: list[dict[str, Any]] = []
    for p in prompts:
        for rep in range(1, repeats + 1):
            if calls:
                time.sleep(pause_s)  # stay under free-tier rate limits
            t0 = time.perf_counter()
            try:
                ans = ask(cfg, key, p.text)
                rec = response(
                    f"{p.prompt_id}-{rep}", ans.answer_text, p.prompt_id, p.category, rep
                )
                ments = {names[m.brand_id]: m.rank_in_list for m in parse_mentions(rec, bs, "eval")
                         if m.mentioned}  # fmt: skip
                calls.append({"prompt": p.prompt_id, "repeat": rep, "ok": True,
                              "latency_ms": ans.latency_ms, "chars": len(ans.answer_text),
                              "mentions": ments,
                              "domains": {d for u in ans.citations if (d := normalise_domain(u))},
                              "tokens_out": ans.output_tokens})  # fmt: skip
            except Exception as exc:  # stored as a failure, never dropped
                calls.append({"prompt": p.prompt_id, "repeat": rep, "ok": False,
                              "error": f"{type(exc).__name__}: {exc}"[:200],
                              "latency_ms": int((time.perf_counter() - t0) * 1000)})  # fmt: skip

    ok = [c for c in calls if c["ok"]]
    by_prompt: dict[str, list[dict]] = defaultdict(list)
    for c in ok:
        by_prompt[c["prompt"]].append(c)

    agree = {b.name: [] for b in bs}
    rank_same, src_j = [], []
    for reps in by_prompt.values():
        if len(reps) < 2:
            continue
        for b in bs:
            agree[b.name].append(len({b.name in r["mentions"] for r in reps}) == 1)
            ranks = [r["mentions"].get(b.name) for r in reps if b.name in r["mentions"]]
            if len(ranks) >= 2:
                rank_same.append(len(set(ranks)) == 1)
        for a, c in combinations(reps, 2):
            if (j := _jaccard(a["domains"], c["domains"])) is not None:
                src_j.append(j)

    lat = sorted(c["latency_ms"] for c in ok)
    n_stable = sum(len(v) >= 2 for v in by_prompt.values())
    enough = n_stable >= MIN_PROMPTS_FOR_STABILITY
    # Nearest-rank percentile: the smallest value with at least 95% of values at or below it.
    p95 = lat[math.ceil(0.95 * len(lat)) - 1] if lat else None
    return {
        "metrics": {
            "provider": provider,
            "model": cfg.model,
            "calls": len(calls),
            "success_rate": len(ok) / len(calls) if calls else None,
            "latency_ms": {"median": median(lat) if lat else None,
                           "p95": p95},
            "answer_chars_mean": round(mean(c["chars"] for c in ok)) if ok else None,
            "sources_per_answer": round(mean(len(c["domains"]) for c in ok), 1) if ok else None,
            "target_mention_rate": (sum(target in c["mentions"] for c in ok) / len(ok)
                                    if ok else None),
            "prompts_with_repeats": n_stable,
            "stability_reported": enough,
            "mention_agreement": {b: (sum(v) / len(v) if v and enough else None)
                                  for b, v in agree.items()},
            "rank_stability": sum(rank_same) / len(rank_same) if rank_same and enough else None,
            "source_overlap_jaccard": round(mean(src_j), 3) if src_j and enough else None,
            "prompts": [p.prompt_id for p in prompts],
            "repeats": repeats,
        },
        "calls": [{k: (sorted(v) if isinstance(v, set) else v) for k, v in c.items()}
                  for c in calls],
        "failures": [c for c in calls if not c["ok"]],
    }  # fmt: skip
