"""Discovery runner: ask every prompt x provider x repeat and store raw answers in Bronze.

API calls run in a small thread pool; all database writes happen on the calling thread.
Failed calls are retried for transient errors, then stored as error rows (never dropped).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from src.config import ProviderConfig, Settings
from src.discovery.models import (
    DiscoveryInput,
    DiscoveryOutput,
    DiscoveryPlan,
    PromptRow,
    ProviderAnswer,
    ProviderRunSummary,
)
from src.discovery.panel import load_panel, panel_path, select_prompts
from src.discovery.providers import (
    AskFn,
    build_openai_request,
    build_perplexity_request,
    get_api_key,
    get_ask_fn,
)
from src.discovery.repository import RunRepository

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
BACKOFF_S = 2.0

REQUEST_BUILDERS = {"perplexity": build_perplexity_request, "openai": build_openai_request}


# ---------------------------------------------------------------- planning


def resolve_providers(inp: DiscoveryInput, settings: Settings) -> list[ProviderConfig]:
    enabled = [p for p in settings.project.providers if p.enabled]
    if inp.providers is None:
        return enabled
    names = {p.name for p in enabled}
    unknown = set(inp.providers) - names
    if unknown:
        raise ValueError(f"Providers not enabled in config: {sorted(unknown)}")
    return [p for p in enabled if p.name in inp.providers]


def load_prompts(inp: DiscoveryInput) -> list[PromptRow]:
    rows = load_panel(panel_path(inp.panel_version))
    return select_prompts(rows, inp.prompt_ids, inp.limit)


def plan_discovery(inp: DiscoveryInput, settings: Settings) -> DiscoveryPlan:
    """Dry run: count the calls a run would make. Makes no API or DB calls."""
    prompts = load_prompts(inp)
    providers = resolve_providers(inp, settings)
    return DiscoveryPlan(
        panel_version=inp.panel_version,
        n_prompts=len(prompts),
        providers=[p.name for p in providers],
        repeats=inp.repeats,
        n_calls=len(prompts) * len(providers) * inp.repeats,
        missing_keys=[p.name for p in providers if not get_api_key(settings, p.name)],
    )


# ---------------------------------------------------------------- retries


def status_of(exc: BaseException) -> int | None:
    """HTTP status from an httpx or openai exception, if there is one."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):  # timeouts, connection errors
        return True
    if type(exc).__name__ in {"APIConnectionError", "APITimeoutError"}:  # openai SDK
        return True
    return status_of(exc) in RETRYABLE_STATUS


def call_with_retry(
    ask: AskFn,
    cfg: ProviderConfig,
    api_key: str,
    question: str,
    sleep: Callable[[float], None] = time.sleep,
) -> ProviderAnswer:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return ask(cfg, api_key, question)
        except Exception as exc:
            if attempt == MAX_ATTEMPTS or not is_retryable(exc):
                raise
            wait = BACKOFF_S * 2 ** (attempt - 1)
            logger.warning(
                "%s attempt %d failed (%s); retrying in %.0fs", cfg.name, attempt, exc, wait
            )
            sleep(wait)
    raise RuntimeError("unreachable")


# ---------------------------------------------------------------- run


def run_discovery(
    inp: DiscoveryInput,
    settings: Settings,
    repo: RunRepository,
    ask_fns: Mapping[str, AskFn] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> DiscoveryOutput:
    """Run the panel against each provider. One bronze_runs row per provider.

    Raises RuntimeError before any call if a needed API key is missing.
    """
    prompts = load_prompts(inp)
    providers = resolve_providers(inp, settings)
    missing = [p.name for p in providers if not get_api_key(settings, p.name)]
    if missing:
        raise RuntimeError(
            f"Missing API key(s) for {missing}. Add them to .env "
            f"({', '.join(n.upper() + '_API_KEY' for n in missing)})."
        )

    summaries = []
    for cfg in providers:
        ask = (ask_fns or {}).get(cfg.name) or get_ask_fn(cfg.name)
        summaries.append(
            _run_one_provider(inp, settings, repo, cfg, ask, prompts, sleep, on_progress)
        )
    return DiscoveryOutput(panel_version=inp.panel_version, runs=summaries)


def _run_one_provider(
    inp: DiscoveryInput,
    settings: Settings,
    repo: RunRepository,
    cfg: ProviderConfig,
    ask: AskFn,
    prompts: list[PromptRow],
    sleep: Callable[[float], None],
    on_progress: Callable[[str, int, int], None] | None,
) -> ProviderRunSummary:
    api_key = get_api_key(settings, cfg.name) or ""
    snapshot = {
        "project": settings.project.project,
        "market": settings.project.market,
        "language": settings.project.language,
        "provider": cfg.model_dump(),
        "repeats": inp.repeats,
        "n_prompts": len(prompts),
        "prompt_ids": [p.prompt_id for p in prompts],
    }
    run_id = repo.create_run(
        panel_version=inp.panel_version,
        provider=cfg.name,
        model=cfg.model,
        config_snapshot=snapshot,
        run_type=inp.run_type,
        notes=inp.notes,
    )
    logger.info("Run %s started: %s x %d prompts x %d", run_id, cfg.name, len(prompts), inp.repeats)

    tasks = [(p, r) for p in prompts for r in range(1, inp.repeats + 1)]
    n_ok = n_failed = 0
    cost = 0.0
    any_cost = False
    try:
        with ThreadPoolExecutor(max_workers=inp.max_workers) as pool:
            futures = {
                pool.submit(call_with_retry, ask, cfg, api_key, p.text, sleep): (p, r)
                for p, r in tasks
            }
            for done, fut in enumerate(as_completed(futures), start=1):
                prompt, repeat_no = futures[fut]
                try:
                    answer = fut.result()
                except Exception as exc:
                    n_failed += 1
                    logger.error("%s %s#%d failed: %s", cfg.name, prompt.prompt_id, repeat_no, exc)
                    repo.save_error(
                        run_id=run_id,
                        prompt_id=prompt.prompt_id,
                        repeat_no=repeat_no,
                        provider=cfg.name,
                        model=cfg.model,
                        request=REQUEST_BUILDERS.get(cfg.name, _generic_request)(cfg, prompt.text),
                        error=f"{type(exc).__name__}: {exc}"[:2000],
                        http_status=status_of(exc),
                    )
                else:
                    n_ok += 1
                    if answer.cost_usd is not None:
                        cost += answer.cost_usd
                        any_cost = True
                    repo.save_answer(
                        run_id=run_id,
                        prompt_id=prompt.prompt_id,
                        repeat_no=repeat_no,
                        provider=cfg.name,
                        answer=answer,
                    )
                if on_progress:
                    on_progress(cfg.name, done, len(tasks))
    except Exception:
        logger.exception("Run %s aborted", run_id)
        repo.finish_run(run_id, "failed")
        raise

    status = "completed" if n_failed == 0 else ("failed" if n_ok == 0 else "partial")
    repo.finish_run(run_id, status)
    logger.info("Run %s %s: %d ok, %d failed", run_id, status, n_ok, n_failed)
    return ProviderRunSummary(
        run_id=run_id,
        provider=cfg.name,
        model=cfg.model,
        n_ok=n_ok,
        n_failed=n_failed,
        cost_usd=round(cost, 6) if any_cost else None,
        status=status,
    )


def _generic_request(cfg: ProviderConfig, question: str) -> dict[str, str]:
    return {"model": cfg.model, "input": question}
