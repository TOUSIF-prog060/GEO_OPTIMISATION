"""Approved knowledge base: read Markdown docs with front matter, chunk, embed."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from src.config import ROOT_DIR, AnalysisConfig
from src.copilot.models import Chunk, KnowledgeDoc

KNOWLEDGE_DIR = ROOT_DIR / "data" / "knowledge"
CHUNK_CHARS = 900
OVERLAP_CHARS = 150
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)

EmbedFn = Callable[[AnalysisConfig, str, list[str]], list[list[float]]]


def parse_doc(path: Path) -> KnowledgeDoc:
    raw = path.read_text(encoding="utf-8")
    m = _FRONT.match(raw)
    if not m:
        raise ValueError(
            f"{path.name}: missing '---' front matter (title, source_url, verified_at)"
        )
    meta: dict[str, Any] = yaml.safe_load(m.group(1)) or {}
    missing = {"title", "source_url", "verified_at"} - set(meta)
    if missing:
        raise ValueError(f"{path.name}: front matter missing {sorted(missing)}")
    text = m.group(2).strip()
    if not text:
        raise ValueError(f"{path.name}: no text")
    return KnowledgeDoc(
        doc_id=path.stem,
        title=str(meta["title"]),
        source_url=str(meta["source_url"]),
        verified_at=meta["verified_at"],
        text=text,
        content_sha=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def load_docs(directory: Path = KNOWLEDGE_DIR) -> list[KnowledgeDoc]:
    files = sorted(p for p in directory.glob("*.md") if p.name.lower() != "readme.md")
    return [parse_doc(p) for p in files]


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Paragraph-aware chunks of about `size` chars; long paragraphs are split with overlap."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        while len(p) > size:  # split an oversized paragraph
            if buf:
                chunks.append(buf)
                buf = ""
            cut = p.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            chunks.append(p[:cut].strip())
            p = p[max(0, cut - overlap) :].strip()
        if len(buf) + len(p) + 2 > size and buf:
            chunks.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks


def doc_chunks(doc: KnowledgeDoc) -> list[Chunk]:
    return [
        Chunk(doc_id=doc.doc_id, chunk_no=i, text=t, title=doc.title, source_url=doc.source_url)
        for i, t in enumerate(chunk_text(doc.text))
    ]


def embed_texts(
    cfg: AnalysisConfig, api_key: str, texts: list[str], client: Any | None = None
) -> list[list[float]]:
    from openai import OpenAI  # lazy

    sdk = client or OpenAI(api_key=api_key, timeout=cfg.timeout_s)
    out: list[list[float]] = []
    for i in range(0, len(texts), 64):
        resp = sdk.embeddings.create(model=cfg.embedding_model, input=texts[i : i + 64])
        out.extend(d.embedding for d in resp.data)
    return out


def to_vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"
