"""Postgres (Supabase) connection helper and a minimal migration runner."""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

from src.config import ROOT_DIR, get_settings

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = ROOT_DIR / "db" / "migrations"

_CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);
"""


def get_conn(db_url: str | None = None) -> psycopg.Connection:
    """Open a new connection. Caller closes it (use `with get_conn() as conn:`)."""
    url = db_url or get_settings().require("supabase_db_url")
    return psycopg.connect(url, connect_timeout=10)


def check_connection(db_url: str | None = None) -> tuple[bool, str]:
    """Return (ok, message). Used by the Home page status badge."""
    try:
        with get_conn(db_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT version()")
            row = cur.fetchone()
        return True, row[0] if row else "connected"
    except Exception as exc:  # report every failure to the UI, and log it
        logger.exception("DB connection check failed")
        return False, str(exc)


def list_migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(directory.glob("*.sql"))


def run_migrations(db_url: str | None = None, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply unapplied migrations in filename order. Returns the filenames applied."""
    applied_now: list[str] = []
    with get_conn(db_url) as conn:
        conn.execute(_CREATE_MIGRATIONS_TABLE)
        conn.commit()
        done = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations").fetchall()}
        for path in list_migration_files(directory):
            if path.name in done:
                continue
            logger.info("Applying migration %s", path.name)
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                # Files may record themselves (so they can be pasted into the Supabase editor).
                conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s) ON CONFLICT DO NOTHING",
                    (path.name,),
                )
            applied_now.append(path.name)
    return applied_now


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    applied = run_migrations()
    print(f"Applied: {applied or 'nothing new'}")
