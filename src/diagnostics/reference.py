"""Versioned domain reference data: data/reference/domains_<version>.csv."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from src.config import ROOT_DIR
from src.diagnostics.models import DomainType
from src.diagnostics.parsing import normalise_domain

REFERENCE_DIR = ROOT_DIR / "data" / "reference"


class DomainCsvRow(BaseModel):
    domain: str
    domain_type: DomainType
    brand_name: str | None = None


def domains_path(version: str, directory: Path = REFERENCE_DIR) -> Path:
    return directory / f"domains_{version}.csv"


def load_domains_csv(path: Path) -> list[DomainCsvRow]:
    if not path.exists():
        raise FileNotFoundError(f"Domain reference not found: {path}")
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [
            DomainCsvRow.model_validate({k: v for k, v in r.items() if v})
            for r in csv.DictReader(f)
        ]
    seen: set[str] = set()
    for r in rows:
        r.domain = normalise_domain(f"https://{r.domain}") or r.domain
        if r.domain in seen:
            raise ValueError(f"{path.name}: duplicate domain {r.domain}")
        seen.add(r.domain)
        if r.domain_type in {"brand_owned", "competitor"} and not r.brand_name:
            raise ValueError(f"{path.name}: {r.domain} is {r.domain_type} but has no brand_name")
    return rows


class ProductCsvRow(BaseModel):
    product_id: str
    product_name: str
    maker: str | None = None
    aliases: list[str] = []
    category: str
    source_url: str
    last_verified_at: date


class FactCsvRow(BaseModel):
    fact_id: str
    subject_type: Literal["brand", "product"]
    subject: str
    attribute: str
    approved_value: str
    value_type: Literal["text", "number", "boolean"]
    tolerance: float | None = None
    source_url: str
    last_verified_at: date


def products_path(version: str, directory: Path = REFERENCE_DIR) -> Path:
    return directory / f"products_{version}.csv"


def facts_path(version: str, directory: Path = REFERENCE_DIR) -> Path:
    return directory / f"reference_facts_{version}.csv"


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Reference file not found: {path}")
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{k: v.strip() for k, v in r.items() if v and v.strip()} for r in csv.DictReader(f)]


def _unique(ids: list[str], name: str) -> None:
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        raise ValueError(f"{name}: duplicate ids {dups}")


def load_products_csv(path: Path) -> list[ProductCsvRow]:
    """Empty list is allowed (catalogue not filled in yet)."""
    rows = []
    for r in _read_rows(path):
        r["aliases"] = [a.strip() for a in r.get("aliases", "").split("|") if a.strip()]
        rows.append(ProductCsvRow.model_validate(r))
    _unique([r.product_id for r in rows], path.name)
    return rows


def load_facts_csv(
    path: Path, brand_names: set[str] | None = None, product_ids: set[str] | None = None
) -> list[FactCsvRow]:
    """Validates that every subject exists (brand in config / product in catalogue)."""
    rows = [FactCsvRow.model_validate(r) for r in _read_rows(path)]
    _unique([r.fact_id for r in rows], path.name)
    for r in rows:
        known = brand_names if r.subject_type == "brand" else product_ids
        if known is not None and r.subject not in known:
            raise ValueError(f"{path.name}: {r.fact_id} has unknown {r.subject_type} '{r.subject}'")
        if r.value_type != "number" and r.tolerance is not None:
            raise ValueError(f"{path.name}: {r.fact_id} tolerance only applies to numbers")
    return rows
