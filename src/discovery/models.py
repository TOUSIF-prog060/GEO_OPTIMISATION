"""Typed inputs and outputs for the discovery engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

CUSTOM_PANEL = "custom"  # prompt set for questions typed in by a user


class PromptRow(BaseModel):
    """One row of the prompt panel CSV."""

    prompt_id: str = Field(min_length=1)
    text: str = Field(min_length=5)
    category: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    language: str = "en"

    @field_validator("prompt_id", "text", "category", "intent", "language")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class ProviderAnswer(BaseModel):
    """What one provider returned for one question. `raw` is the untouched API payload."""

    answer_text: str
    citations: list[str] = Field(default_factory=list)
    model: str
    request: dict[str, Any]  # exact payload sent, never contains the API key
    raw: dict[str, Any]
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    http_status: int | None = 200


class DiscoveryInput(BaseModel):
    panel_version: str = Field(min_length=1)
    providers: list[str] | None = None  # None = every enabled provider in the config
    repeats: int = Field(default=1, ge=1, le=10)
    prompt_ids: list[str] | None = None  # None = whole panel
    limit: int | None = Field(default=None, ge=1)  # first N prompts, for small test runs
    max_workers: int = Field(default=4, ge=1, le=16)
    run_type: str = "baseline"
    notes: str | None = None
    # Questions typed in by a user instead of a panel CSV (panel_version must be "custom").
    custom_prompts: list[PromptRow] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _custom_needs_custom_panel(self) -> DiscoveryInput:
        if self.custom_prompts is not None:
            if self.panel_version != CUSTOM_PANEL:
                raise ValueError(f"custom_prompts need panel_version='{CUSTOM_PANEL}'")
            if not self.custom_prompts:
                raise ValueError("custom_prompts is empty")
        return self


class ProviderRunSummary(BaseModel):
    run_id: str
    provider: str
    model: str
    n_ok: int
    n_failed: int
    cost_usd: float | None
    status: str


class DiscoveryOutput(BaseModel):
    panel_version: str
    runs: list[ProviderRunSummary]

    @property
    def run_ids(self) -> list[str]:
        return [r.run_id for r in self.runs]


class DiscoveryPlan(BaseModel):
    """Dry-run result: what would be called, without calling anything."""

    panel_version: str
    n_prompts: int
    providers: list[str]
    repeats: int
    n_calls: int
    missing_keys: list[str]
