"""Embed approved brand documents from data/knowledge/ into the knowledge base (pgvector).

python scripts/ingest_knowledge.py          # needs OPENAI_API_KEY; unchanged files are skipped
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402
from src.copilot import ingest_knowledge  # noqa: E402
from src.copilot.repository import PostgresCopilotRepository  # noqa: E402
from src.db import get_conn  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with get_conn() as conn:
        out = ingest_knowledge(get_settings(), PostgresCopilotRepository(conn))
    print(f"{out.n_docs} documents · {out.n_chunks} chunks embedded · "
          f"{out.n_skipped_unchanged} unchanged")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
