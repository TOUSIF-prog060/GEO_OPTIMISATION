"""Load secrets from .env and project config from configs/*.yaml into typed objects."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "configs" / "beauty_india.yaml"


class Brand(BaseModel):
    name: str
    is_target: bool = False
    aliases: list[str] = Field(min_length=1)


class ProviderConfig(BaseModel):
    name: str
    model: str
    enabled: bool = True
    timeout_s: float = 60.0
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    price_per_request: float | None = None


class ProjectConfig(BaseModel):
    project: str
    market: str
    language: str
    brands: list[Brand]
    providers: list[ProviderConfig]

    @model_validator(mode="after")
    def _exactly_one_target(self) -> ProjectConfig:
        targets = [b for b in self.brands if b.is_target]
        if len(targets) != 1:
            raise ValueError(f"Expected exactly one target brand, found {len(targets)}")
        return self

    @property
    def target(self) -> Brand:
        return next(b for b in self.brands if b.is_target)

    @property
    def competitors(self) -> list[Brand]:
        return [b for b in self.brands if not b.is_target]

    def provider(self, name: str) -> ProviderConfig:
        for p in self.providers:
            if p.name == name:
                return p
        raise KeyError(f"Provider '{name}' not in config")


class Settings(BaseModel):
    supabase_db_url: str | None = None
    perplexity_api_key: str | None = None
    openai_api_key: str | None = None
    project: ProjectConfig

    def require(self, field: str) -> str:
        """Return a secret, or raise a clear error if it is not set."""
        value = getattr(self, field)
        if not value:
            raise RuntimeError(f"{field.upper()} is not set. Add it to .env (see .env.example).")
        return value


def load_project_config(path: Path | str = DEFAULT_CONFIG_PATH) -> ProjectConfig:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ProjectConfig.model_validate(data)


@lru_cache
def get_settings(config_path: str = str(DEFAULT_CONFIG_PATH)) -> Settings:
    load_dotenv(ROOT_DIR / ".env")
    return Settings(
        supabase_db_url=os.getenv("SUPABASE_DB_URL") or None,
        perplexity_api_key=os.getenv("PERPLEXITY_API_KEY") or None,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        project=load_project_config(config_path),
    )
