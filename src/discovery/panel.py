"""Prompt panel: load and validate the CSV, sync brands and prompts into the database."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import psycopg

from src.config import ROOT_DIR, ProjectConfig
from src.discovery.models import PromptRow

logger = logging.getLogger(__name__)

REFERENCE_DIR = ROOT_DIR / "data" / "reference"
REQUIRED_COLUMNS = {"prompt_id", "text", "category", "intent"}


def panel_path(panel_version: str, directory: Path = REFERENCE_DIR) -> Path:
    return directory / f"prompt_panel_{panel_version}.csv"


def load_panel(path: Path) -> list[PromptRow]:
    """Read and validate a panel CSV. Raises ValueError on missing columns or duplicates."""
    if not path.exists():
        raise FileNotFoundError(f"Prompt panel not found: {path}")
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
        rows = [PromptRow.model_validate({k: v for k, v in r.items() if v}) for r in reader]
    if not rows:
        raise ValueError(f"{path.name}: no prompts")
    _check_unique(rows, path.name)
    return rows


def _check_unique(rows: list[PromptRow], name: str) -> None:
    ids = [r.prompt_id for r in rows]
    texts = [r.text.lower() for r in rows]
    dup_ids = {i for i in ids if ids.count(i) > 1}
    dup_texts = {t for t in texts if texts.count(t) > 1}
    if dup_ids:
        raise ValueError(f"{name}: duplicate prompt_id {sorted(dup_ids)}")
    if dup_texts:
        raise ValueError(f"{name}: duplicate prompt text {sorted(dup_texts)[:3]}")


def select_prompts(
    rows: list[PromptRow], prompt_ids: list[str] | None = None, limit: int | None = None
) -> list[PromptRow]:
    if prompt_ids:
        wanted = set(prompt_ids)
        unknown = wanted - {r.prompt_id for r in rows}
        if unknown:
            raise ValueError(f"Unknown prompt_ids: {sorted(unknown)}")
        rows = [r for r in rows if r.prompt_id in wanted]
    return rows[:limit] if limit else rows


def sync_brands(conn: psycopg.Connection, project: ProjectConfig) -> int:
    """Upsert brands from the YAML config. Returns the number of brands written."""
    with conn.cursor() as cur:
        for b in project.brands:
            cur.execute(
                """
                INSERT INTO brands (name, aliases, market, is_target)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE
                SET aliases = EXCLUDED.aliases, market = EXCLUDED.market,
                    is_target = EXCLUDED.is_target
                """,
                (b.name, b.aliases, project.market, b.is_target),
            )
    conn.commit()
    logger.info("Synced %d brands", len(project.brands))
    return len(project.brands)


def sync_prompts(conn: psycopg.Connection, rows: list[PromptRow], panel_version: str) -> int:
    """Insert prompts for a panel version. Existing prompt_ids are left unchanged
    (a changed prompt must get a new id or a new panel version)."""
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO prompts (prompt_id, text, category, intent, language, panel_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (prompt_id) DO NOTHING
                """,
                (r.prompt_id, r.text, r.category, r.intent, r.language, panel_version),
            )
    conn.commit()
    logger.info("Synced %d prompts for panel %s", len(rows), panel_version)
    return len(rows)
