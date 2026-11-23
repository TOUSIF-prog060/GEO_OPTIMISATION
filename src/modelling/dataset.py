"""Load the team's collection workbook, freeze it, and build the modelling table.

One row per usable answer. The target is whether the brand is named, found with the same alias
rules as the diagnostics reader. Every row keeps the sheet's run_id as its response_id.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

import pandas as pd

from src.config import Brand
from src.diagnostics.parsing import alias_pattern

log = logging.getLogger(__name__)

SHEET = "Final_Data"
REQUIRED_COLUMNS = [
    "run_id",
    "engine",
    "run_no",
    "prompt_id",
    "language",
    "question_type",
    "category",
    "collection_method",
    "full_response_text",
    "use_in_model",
]
# Team-computed word-search flags (raw workbook name, clean data-v1.0 name), used only to
# report agreement with our alias reader.
SHEET_WORD_FLAG = {
    "Sephora India": ("sephora_word_in_answer", "sephora_named"),
    "Nykaa": ("nykaa_word_in_answer", "nykaa_named"),
}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def freeze_workbook(path: Path, raw_dir: Path) -> tuple[Path, str]:
    """Copy the workbook, unchanged, to raw_dir under a name carrying its checksum."""
    sha = file_sha256(path)
    raw_dir.mkdir(parents=True, exist_ok=True)
    frozen = raw_dir / f"{path.stem}_{sha[:10]}{path.suffix}"
    if not frozen.exists():
        shutil.copy2(path, frozen)
        log.info("Froze %s as %s", path, frozen)
    return frozen, sha


def read_final_data(path: Path) -> pd.DataFrame:
    """Raw collection workbook (sheet Final_Data) or the clean data-v1.0 CSV."""
    dtypes = {"run_id": str, "prompt_id": str, "base_id": str}
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=dtypes)
    else:
        df = pd.read_excel(path, sheet_name=SHEET, dtype=dtypes)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Sheet {SHEET} is missing columns: {', '.join(missing)}")
    return df


def _clean(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip().str.lower()


def slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")


def label_brands(texts: pd.Series, brands: list[Brand]) -> pd.DataFrame:
    """named_<brand> columns: True when any alias of the brand appears in the answer."""
    out = {}
    for b in brands:
        pattern = alias_pattern(b.aliases + [b.name])
        out[f"named_{slug(b.name)}"] = (
            texts.fillna("").astype(str).map(lambda t, p=pattern: bool(p.search(t)))
        )
    return pd.DataFrame(out, index=texts.index)


def build_features(
    raw: pd.DataFrame,
    brands: list[Brand],
    target: str,
    factors: list[str],
    strict: bool = False,
) -> tuple[pd.DataFrame, dict[str, int], float | None]:
    """Usable rows with factors, group_id and target y. Returns (table, excluded, agreement).

    strict=True also drops rows the team marked use_strict = FALSE (repeated text, suspect
    answers), for sensitivity checks."""
    df = raw.copy()
    df["use_in_model"] = _clean(df["use_in_model"])
    text = df["full_response_text"].astype("string").str.strip()
    excluded = {
        "use_in_model = no": int((df["use_in_model"] != "yes").sum()),
        "empty answer": int(((df["use_in_model"] == "yes") & (text.fillna("") == "")).sum()),
    }
    keep = (df["use_in_model"] == "yes") & (text.fillna("") != "")
    if strict:
        if "use_strict" not in df:
            raise ValueError("strict=True needs a use_strict column (clean data-v1.0 CSV)")
        strict_ok = _clean(df["use_strict"]).isin(["true", "1", "yes"])
        excluded["use_strict = false"] = int((keep & ~strict_ok).sum())
        keep &= strict_ok
    df = df[keep].copy()
    missing_factor = df[factors].isna().any(axis=1)
    excluded["missing factor value"] = int(missing_factor.sum())
    df = df[~missing_factor]

    labels = label_brands(df["full_response_text"], brands)
    df = pd.concat([df, labels], axis=1)
    target_col = f"named_{slug(target)}"
    if target_col not in df:
        raise ValueError(f"Unknown target brand: {target}")

    agreement = None
    flag = next((c for c in SHEET_WORD_FLAG.get(target, ()) if c in df), None)
    if flag:
        sheet = _clean(df[flag]).isin(["true", "1", "yes"])
        agreement = float((sheet == df[target_col]).mean()) if len(df) else None

    table = pd.DataFrame(
        {
            "response_id": df["run_id"].astype(str),
            "prompt_id": df["prompt_id"].astype(str).str.strip(),
            # English and Hinglish twins (B01E / B01H) share a group and stay in one fold.
            "group_id": (
                df["base_id"].astype(str).str.strip()
                if "base_id" in df
                else df["prompt_id"].astype(str).str.strip().str[:3]
            ),
            "run_no": pd.to_numeric(df["run_no"], errors="coerce"),
        }
    )
    for f in factors:
        table[f] = _clean(df[f]).astype(str)
    for col in labels.columns:
        table[col] = df[col].astype(bool)
    table["y"] = df[target_col].astype(int)
    return table.reset_index(drop=True), excluded, agreement


def design_matrix(
    table: pd.DataFrame, factors: list[str]
) -> tuple[pd.DataFrame, dict[str, str], dict[str, str], dict[str, list[str]]]:
    """One-hot factors. The most common level of each factor is the reference.

    Returns (X, reference_levels, dropped duplicate columns, factor -> its columns). A column
    identical to an earlier one (e.g. category=retailer and question_type=where_to_buy) is
    dropped so the logistic model stays identifiable.
    """
    refs: dict[str, str] = {}
    parts = []
    for f in factors:
        counts = table[f].value_counts()
        ref = str(sorted(counts[counts == counts.max()].index)[0])
        refs[f] = ref
        levels = sorted(lv for lv in table[f].unique() if lv != ref)
        for lv in levels:
            parts.append(pd.Series((table[f] == lv).astype(float), name=f"{f}={lv}"))
    X = pd.concat(parts, axis=1) if parts else pd.DataFrame(index=table.index)

    dropped: dict[str, str] = {}
    seen: dict[bytes, str] = {}
    for col in list(X.columns):
        key = X[col].to_numpy().tobytes()
        if key in seen:
            dropped[col] = seen[key]
            X = X.drop(columns=col)
        elif X[col].nunique() < 2:
            dropped[col] = "(constant)"
            X = X.drop(columns=col)
        else:
            seen[key] = col
    groups = {f: [c for c in X.columns if c.startswith(f + "=")] for f in factors}
    return X, refs, dropped, groups
