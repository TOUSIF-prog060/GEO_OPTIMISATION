from datetime import datetime

from src.reporting import kpi_deltas, leader_by_provider


def row(provider, day, brand, target, rate, n=30):
    return {"provider": provider, "started_at": datetime(2026, 11, day), "brand": brand,
            "is_target": target, "mention_rate": rate, "n_responses": n}  # fmt: skip


HISTORY = [
    row("perplexity", 1, "Sephora India", True, 0.20),
    row("perplexity", 1, "Nykaa", False, 0.80),
    row("perplexity", 8, "Sephora India", True, 0.35),
    row("perplexity", 8, "Nykaa", False, 0.75),
    row("openai", 8, "Sephora India", True, 0.50),
    row("openai", 8, "Nykaa", False, 0.40),
]


def test_kpi_deltas_vs_previous_run_per_provider() -> None:
    k = {x["provider"]: x for x in kpi_deltas(HISTORY)}
    assert k["perplexity"]["value"] == 0.35 and k["perplexity"]["delta"] == 0.15
    assert k["openai"]["delta"] is None  # only one run


def test_leader_by_provider_uses_latest_run() -> None:
    assert leader_by_provider(HISTORY) == {"perplexity": "Nykaa", "openai": "Sephora India"}


def test_empty_history() -> None:
    assert kpi_deltas([]) == [] and leader_by_provider([]) == {}
