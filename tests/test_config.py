import pytest
from pydantic import ValidationError

from src.config import ProjectConfig, load_project_config


@pytest.fixture
def cfg() -> ProjectConfig:
    return load_project_config()


def test_yaml_loads(cfg: ProjectConfig) -> None:
    assert cfg.market == "IN"
    assert cfg.language == "en"


def test_one_target_and_two_competitors(cfg: ProjectConfig) -> None:
    assert cfg.target.name == "Sephora India"
    assert {b.name for b in cfg.competitors} == {"Nykaa", "Tira"}


def test_every_brand_has_aliases(cfg: ProjectConfig) -> None:
    for brand in cfg.brands:
        assert brand.aliases, brand.name
    assert "sephora.in" in cfg.target.aliases


def test_providers_have_models_from_config(cfg: ProjectConfig) -> None:
    names = {p.name for p in cfg.providers}
    assert {"perplexity", "openai"} <= names
    for p in cfg.providers:
        assert p.model.strip()


def test_unknown_provider_raises(cfg: ProjectConfig) -> None:
    with pytest.raises(KeyError):
        cfg.provider("does-not-exist")


def test_two_targets_rejected() -> None:
    data = {
        "project": "x",
        "market": "IN",
        "language": "en",
        "brands": [
            {"name": "A", "is_target": True, "aliases": ["A"]},
            {"name": "B", "is_target": True, "aliases": ["B"]},
        ],
        "providers": [],
    }
    with pytest.raises(ValidationError):
        ProjectConfig.model_validate(data)
