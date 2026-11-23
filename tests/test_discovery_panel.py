from pathlib import Path

import pytest

from src.discovery.panel import load_panel, panel_path, select_prompts

HEADER = "prompt_id,text,category,intent\n"


def write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "prompt_panel_t.csv"
    p.write_text(HEADER + body, encoding="utf-8")
    return p


def test_v0_panel_is_valid() -> None:
    rows = load_panel(panel_path("v0"))
    assert len(rows) >= 20
    assert all(r.language == "en" for r in rows)


def test_missing_column(tmp_path: Path) -> None:
    p = tmp_path / "bad.csv"
    p.write_text("prompt_id,text\nA,hello world\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        load_panel(p)


def test_duplicate_ids_rejected(tmp_path: Path) -> None:
    p = write(tmp_path, "A,first question,c,i\nA,second question,c,i\n")
    with pytest.raises(ValueError, match="duplicate prompt_id"):
        load_panel(p)


def test_duplicate_text_rejected_case_insensitive(tmp_path: Path) -> None:
    p = write(tmp_path, "A,Best sunscreen?,c,i\nB,best sunscreen?,c,i\n")
    with pytest.raises(ValueError, match="duplicate prompt text"):
        load_panel(p)


def test_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_panel(Path("does/not/exist.csv"))


def test_select_prompts(tmp_path: Path) -> None:
    rows = load_panel(
        write(tmp_path, "A,question one,c,i\nB,question two,c,i\nC,question three,c,i\n")
    )
    assert [r.prompt_id for r in select_prompts(rows, limit=2)] == ["A", "B"]
    assert [r.prompt_id for r in select_prompts(rows, prompt_ids=["C"])] == ["C"]
    with pytest.raises(ValueError, match="Unknown"):
        select_prompts(rows, prompt_ids=["Z"])
