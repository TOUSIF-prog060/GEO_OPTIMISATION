from typing import Any

import httpx
import pytest

from src.config import ProviderConfig, Settings, load_project_config
from src.discovery.models import DiscoveryInput, ProviderAnswer
from src.discovery.runner import call_with_retry, is_retryable, plan_discovery, run_discovery


class FakeRepo:
    """In-memory stand-in for PostgresRunRepository."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.responses: list[dict[str, Any]] = []

    def create_run(self, **kw: Any) -> str:
        run_id = f"run-{len(self.runs) + 1}"
        self.runs[run_id] = {**kw, "status": "running"}
        return run_id

    def save_answer(self, **kw: Any) -> str:
        self.responses.append({**kw, "error": None})
        return f"resp-{len(self.responses)}"

    def save_error(self, **kw: Any) -> str:
        self.responses.append(kw)
        return f"resp-{len(self.responses)}"

    def finish_run(self, run_id: str, status: str) -> None:
        self.runs[run_id]["status"] = status


def settings(with_keys: bool = True) -> Settings:
    return Settings(
        project=load_project_config(),
        perplexity_api_key="pk" if with_keys else None,
        openai_api_key="ok" if with_keys else None,
        gemini_api_key="gk" if with_keys else None,
    )


def fake_answer(cfg: ProviderConfig, key: str, q: str) -> ProviderAnswer:
    return ProviderAnswer(
        answer_text=f"{cfg.name}: {q}",
        model=cfg.model,
        request={"q": q},
        raw={"q": q},
        latency_ms=1,
        cost_usd=0.01,
    )


def test_plan_without_keys_reports_missing() -> None:
    plan = plan_discovery(DiscoveryInput(panel_version="v0", limit=5, repeats=2), settings(False))
    assert plan.n_calls == 5 * 2 * len(plan.providers)
    assert set(plan.missing_keys) == set(plan.providers)


def test_run_refuses_without_keys() -> None:
    repo = FakeRepo()
    with pytest.raises(RuntimeError, match="Missing API key"):
        run_discovery(DiscoveryInput(panel_version="v0", limit=1), settings(False), repo)
    assert repo.runs == {}  # nothing written, nothing called


def test_run_stores_every_answer_with_lineage() -> None:
    repo = FakeRepo()
    fns = {"perplexity": fake_answer, "openai": fake_answer, "gemini": fake_answer}
    out = run_discovery(
        DiscoveryInput(panel_version="v0", limit=3, repeats=2), settings(), repo, ask_fns=fns
    )

    assert len(out.runs) == 3
    assert len(repo.responses) == 3 * 2 * 3
    for r in out.runs:
        assert r.status == "completed" and r.n_ok == 6 and r.n_failed == 0
        assert r.cost_usd == pytest.approx(0.06)
        assert repo.runs[r.run_id]["status"] == "completed"
    keys = {(x["run_id"], x["prompt_id"], x["repeat_no"]) for x in repo.responses}
    assert len(keys) == len(repo.responses)  # unique per run/prompt/repeat


def test_failures_are_stored_not_dropped() -> None:
    def flaky(cfg: ProviderConfig, key: str, q: str) -> ProviderAnswer:
        if "sunscreen" in q.lower():
            raise ValueError("bad payload")
        return fake_answer(cfg, key, q)

    repo = FakeRepo()
    out = run_discovery(
        DiscoveryInput(panel_version="v0", providers=["perplexity"]),
        settings(),
        repo,
        ask_fns={"perplexity": flaky},
    )
    run = out.runs[0]
    assert run.status == "partial" and run.n_failed > 0
    errors = [x for x in repo.responses if x.get("error")]
    assert len(errors) == run.n_failed
    assert all("ValueError" in e["error"] and e["request"] for e in errors)


def test_retry_on_transient_then_success() -> None:
    attempts = {"n": 0}
    req = httpx.Request("POST", "https://x")

    def flaky(cfg: ProviderConfig, key: str, q: str) -> ProviderAnswer:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise httpx.HTTPStatusError(
                "busy", request=req, response=httpx.Response(429, request=req)
            )
        return fake_answer(cfg, key, q)

    waits: list[float] = []
    cfg = ProviderConfig(name="perplexity", model="sonar")
    ans = call_with_retry(flaky, cfg, "k", "q", sleep=waits.append)
    assert ans.answer_text and attempts["n"] == 3 and waits == [2.0, 4.0]


def test_no_retry_on_client_error() -> None:
    req = httpx.Request("POST", "https://x")
    exc = httpx.HTTPStatusError("bad", request=req, response=httpx.Response(401, request=req))
    assert not is_retryable(exc)
    assert is_retryable(httpx.ConnectTimeout("t"))


def test_unknown_provider_rejected() -> None:
    with pytest.raises(ValueError, match="not enabled"):
        plan_discovery(DiscoveryInput(panel_version="v0", providers=["unknown"]), settings())


# ---------------------------------------------------------------- custom questions


def test_custom_prompt_id_is_stable_and_normalised() -> None:
    from src.discovery.panel import custom_prompt

    a = custom_prompt("Best  sunscreen in India?")
    b = custom_prompt("best sunscreen in india?  ")
    assert a.prompt_id == b.prompt_id and a.prompt_id.startswith("CUS-")
    assert a.text == "Best sunscreen in India?" and a.category == "custom"
    assert custom_prompt("Best serum in India?").prompt_id != a.prompt_id


def test_custom_prompts_need_custom_panel() -> None:
    from src.discovery.panel import custom_prompt

    p = custom_prompt("Where to buy Korean skincare in India?")
    with pytest.raises(ValueError, match="custom"):
        DiscoveryInput(panel_version="v0", custom_prompts=[p])
    with pytest.raises(ValueError, match="empty"):
        DiscoveryInput(panel_version="custom", custom_prompts=[])


def test_run_custom_questions_as_adhoc() -> None:
    from src.discovery.panel import custom_prompt

    prompts = [custom_prompt("Is Sephora India cheaper than Nykaa?"),
               custom_prompt("Where to buy Huda Beauty in India?")]  # fmt: skip
    inp = DiscoveryInput(panel_version="custom", providers=["gemini"], run_type="adhoc",
                         custom_prompts=prompts)  # fmt: skip
    assert plan_discovery(inp, settings()).n_calls == 2
    repo = FakeRepo()
    out = run_discovery(inp, settings(), repo, ask_fns={"gemini": fake_answer})
    assert out.runs[0].n_ok == 2
    assert repo.runs[out.run_ids[0]]["run_type"] == "adhoc"
    assert {r["prompt_id"] for r in repo.responses} == {p.prompt_id for p in prompts}
