"""Human validation of the diagnostics parser (charter D4/D5 evidence).

Workflow
  1. draw_sample()        stratified random sample of responses (provider x category), seeded
  2. write_sheet()        one CSV per labeller: response x brand rows with blank label columns
  3. read_sheet()         validate a filled-in CSV
  4. evaluate()           system output vs human reference:
                          - reference = items where all labellers agree (disagreements are
                            reported and excluded)
                          - mentioned / is_recommended: precision, recall, F1
                          - rank_in_list: exact-match accuracy where both say "mentioned"
                          - sentiment: accuracy and macro-F1 where both have a label
                          - inter-labeller agreement: Cohen's kappa (first two labellers)
All metrics are plain Python, so no extra dependency is needed.
"""

from __future__ import annotations

import csv
import random
from collections import Counter, defaultdict
from collections.abc import Hashable, Sequence
from pathlib import Path

import psycopg
from pydantic import BaseModel, field_validator

from src.diagnostics.models import BrandRef, MentionRow, ResponseRecord, Sentiment

SHEET_COLUMNS = [
    "sample_version", "response_id", "brand", "prompt_text", "answer_text",
    "mentioned", "rank_in_list", "sentiment", "is_recommended", "notes",
]  # fmt: skip
_TRUE = {"1", "y", "yes", "true", "t"}
_FALSE = {"0", "n", "no", "false", "f"}


# ---------------------------------------------------------------- sampling


def draw_sample(responses: list[ResponseRecord], n: int, seed: int = 42) -> list[ResponseRecord]:
    """Proportional stratified sample by provider|category; every stratum gets >= 1 if n allows."""
    ok = sorted((r for r in responses if r.ok), key=lambda r: r.response_id)
    if n >= len(ok):
        return ok
    strata: dict[str, list[ResponseRecord]] = defaultdict(list)
    for r in ok:
        strata[f"{r.provider}|{r.category}"].append(r)
    rng = random.Random(seed)
    keys = sorted(strata)
    quota = {k: max(1, round(n * len(strata[k]) / len(ok))) for k in keys}
    while sum(quota.values()) > n:  # trim the largest quotas first
        k = max(keys, key=lambda k: (quota[k], k))
        quota[k] -= 1
    picked: list[ResponseRecord] = []
    for k in keys:
        picked.extend(rng.sample(strata[k], min(quota[k], len(strata[k]))))
    return sorted(picked, key=lambda r: r.response_id)


def stratum(r: ResponseRecord) -> str:
    return f"{r.provider}|{r.category}"


# ---------------------------------------------------------------- sheets


def write_sheet(
    path: Path, sample_version: str, sample: list[ResponseRecord], brands: list[BrandRef]
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_COLUMNS)
        w.writeheader()
        for r in sample:
            for b in brands:
                w.writerow(
                    {
                        "sample_version": sample_version,
                        "response_id": r.response_id,
                        "brand": b.name,
                        "prompt_text": r.prompt_text,
                        "answer_text": r.answer_text or "",
                    }
                )
    return len(sample) * len(brands)


class HumanLabel(BaseModel):
    sample_version: str
    response_id: str
    brand: str
    labeller: str
    mentioned: bool
    rank_in_list: int | None = None
    sentiment: Sentiment | None = None
    is_recommended: bool | None = None
    notes: str | None = None

    @field_validator("mentioned", "is_recommended", mode="before")
    @classmethod
    def _yes_no(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip().lower()
            if s in _TRUE:
                return True
            if s in _FALSE:
                return False
            if s == "":
                return None
            raise ValueError(f"expected yes/no, got {v!r}")
        return v

    @field_validator("rank_in_list", "notes", mode="before")
    @classmethod
    def _blank_is_none(cls, v: object) -> object:
        return (v.strip() or None) if isinstance(v, str) else v

    @field_validator("sentiment", mode="before")
    @classmethod
    def _sentiment(cls, v: object) -> object:
        return (v.strip().lower() or None) if isinstance(v, str) else v


def read_sheet(path: Path, labeller: str) -> list[HumanLabel]:
    """Rows with a blank 'mentioned' are treated as not yet labelled and skipped."""
    labels: list[HumanLabel] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            if not (row.get("mentioned") or "").strip():
                continue
            fields = {
                k: row.get(k) for k in SHEET_COLUMNS if k not in {"prompt_text", "answer_text"}
            }
            try:
                labels.append(HumanLabel(labeller=labeller, **fields))
            except ValueError as exc:
                raise ValueError(f"{path.name} line {i}: {exc}") from exc
    return labels


# ---------------------------------------------------------------- metrics


class PRF(BaseModel):
    precision: float | None
    recall: float | None
    f1: float | None
    support: int  # reference positives
    n: int


def binary_prf(y_true: Sequence[bool], y_pred: Sequence[bool]) -> PRF:
    tp = sum(t and p for t, p in zip(y_true, y_pred, strict=True))
    fp = sum((not t) and p for t, p in zip(y_true, y_pred, strict=True))
    fn = sum(t and (not p) for t, p in zip(y_true, y_pred, strict=True))
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if prec == 0 or rec == 0 else None)
    r4 = lambda x: None if x is None else round(x, 4)  # noqa: E731
    return PRF(precision=r4(prec), recall=r4(rec), f1=r4(f1), support=tp + fn, n=len(y_true))


def accuracy(y_true: Sequence[Hashable], y_pred: Sequence[Hashable]) -> float | None:
    if not y_true:
        return None
    return round(sum(a == b for a, b in zip(y_true, y_pred, strict=True)) / len(y_true), 4)


def macro_f1(y_true: Sequence[Hashable], y_pred: Sequence[Hashable]) -> float | None:
    classes = sorted(set(y_true), key=str)
    if not classes:
        return None
    scores = []
    for c in classes:
        res = binary_prf([t == c for t in y_true], [p == c for p in y_pred])
        scores.append(res.f1 or 0.0)
    return round(sum(scores) / len(scores), 4)


def cohen_kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if pe == 1:
        return 1.0 if po == 1 else None
    return round((po - pe) / (1 - pe), 4)


# ---------------------------------------------------------------- evaluation


class EvaluationReport(BaseModel):
    sample_version: str
    labellers: list[str]
    n_items: int  # response x brand pairs labelled by every labeller
    n_disagreements: int
    kappa_mentioned: float | None
    kappa_sentiment: float | None
    mentioned: PRF
    is_recommended: PRF | None
    rank_accuracy: float | None
    rank_n: int
    sentiment_accuracy: float | None
    sentiment_macro_f1: float | None
    sentiment_n: int
    errors: list[dict[str, str]]  # first mismatches, for error analysis


def evaluate(
    sample_version: str,
    labels: list[HumanLabel],
    system: list[MentionRow],
    brand_ids: dict[str, int],
    max_errors: int = 25,
) -> EvaluationReport:
    by_item: dict[tuple[str, str], dict[str, HumanLabel]] = defaultdict(dict)
    for lab in labels:
        by_item[(lab.response_id, lab.brand)][lab.labeller] = lab
    labellers = sorted({lab.labeller for lab in labels})
    full = {k: v for k, v in by_item.items() if set(v) == set(labellers)}

    # inter-labeller agreement on the first two labellers
    k_m = k_s = None
    if len(labellers) >= 2:
        a, b = labellers[:2]
        items = list(full.values())
        k_m = cohen_kappa([i[a].mentioned for i in items], [i[b].mentioned for i in items])
        both = [i for i in items if i[a].sentiment and i[b].sentiment]
        k_s = cohen_kappa([i[a].sentiment for i in both], [i[b].sentiment for i in both])

    # reference = consensus items
    reference: dict[tuple[str, str], HumanLabel] = {}
    disagreements = 0
    for key, by_lab in full.items():
        vals = list(by_lab.values())
        if len({v.mentioned for v in vals}) == 1:
            reference[key] = vals[0]
        else:
            disagreements += 1

    sys_by_key = {(m.response_id, m.brand_id): m for m in system}
    y_true, y_pred, rec_true, rec_pred = [], [], [], []
    rank_t, rank_p, sent_t, sent_p = [], [], [], []
    errors: list[dict[str, str]] = []
    for (rid, brand), ref in sorted(reference.items()):
        m = sys_by_key.get((rid, brand_ids.get(brand, -1)))
        pred = bool(m and m.mentioned)
        y_true.append(ref.mentioned)
        y_pred.append(pred)
        if ref.mentioned != pred and len(errors) < max_errors:
            errors.append({"response_id": rid, "brand": brand, "human": str(ref.mentioned),
                           "system": str(pred), "notes": ref.notes or ""})  # fmt: skip
        if ref.mentioned and pred and m is not None:
            rank_t.append(ref.rank_in_list)
            rank_p.append(m.rank_in_list)
            if ref.sentiment and m.sentiment:
                sent_t.append(ref.sentiment)
                sent_p.append(m.sentiment)
            if ref.is_recommended is not None and m.is_recommended is not None:
                rec_true.append(ref.is_recommended)
                rec_pred.append(m.is_recommended)

    return EvaluationReport(
        sample_version=sample_version,
        labellers=labellers,
        n_items=len(full),
        n_disagreements=disagreements,
        kappa_mentioned=k_m,
        kappa_sentiment=k_s,
        mentioned=binary_prf(y_true, y_pred),
        is_recommended=binary_prf(rec_true, rec_pred) if rec_true else None,
        rank_accuracy=accuracy(rank_t, rank_p),
        rank_n=len(rank_t),
        sentiment_accuracy=accuracy(sent_t, sent_p),
        sentiment_macro_f1=macro_f1(sent_t, sent_p),
        sentiment_n=len(sent_t),
        errors=errors,
    )


# ---------------------------------------------------------------- database


def save_sample(conn: psycopg.Connection, sample_version: str, sample: list[ResponseRecord]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO validation_samples (sample_version, response_id, stratum)
            VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
            """,
            [(sample_version, r.response_id, stratum(r)) for r in sample],
        )
    conn.commit()
    return len(sample)


def sample_exists(conn: psycopg.Connection, sample_version: str) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM validation_samples WHERE sample_version = %s", (sample_version,)
    ).fetchone()
    return bool(row and row[0])


def save_labels(
    conn: psycopg.Connection, labels: list[HumanLabel], brand_ids: dict[str, int]
) -> int:
    unknown = {lab.brand for lab in labels} - set(brand_ids)
    if unknown:
        raise ValueError(f"Unknown brands in sheet: {sorted(unknown)}")
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO validation_labels
              (sample_version, response_id, brand_id, labeller, mentioned, rank_in_list,
               sentiment, is_recommended, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sample_version, response_id, brand_id, labeller) DO UPDATE
            SET mentioned = EXCLUDED.mentioned, rank_in_list = EXCLUDED.rank_in_list,
                sentiment = EXCLUDED.sentiment, is_recommended = EXCLUDED.is_recommended,
                notes = EXCLUDED.notes, labelled_at = now()
            """,
            [
                (
                    lab.sample_version,
                    lab.response_id,
                    brand_ids[lab.brand],
                    lab.labeller,
                    lab.mentioned,
                    lab.rank_in_list,
                    lab.sentiment,
                    lab.is_recommended,
                    lab.notes,
                )
                for lab in labels
            ],  # fmt: skip
        )
    conn.commit()
    return len(labels)


def load_labels(conn: psycopg.Connection, sample_version: str) -> list[HumanLabel]:
    cur = conn.execute(
        """
        SELECT l.sample_version, l.response_id::text, b.name, l.labeller, l.mentioned,
               l.rank_in_list, l.sentiment, l.is_recommended, l.notes
        FROM validation_labels l JOIN brands b USING (brand_id)
        WHERE l.sample_version = %s
        """,
        (sample_version,),
    )
    keys = ["sample_version", "response_id", "brand", "labeller", "mentioned",
            "rank_in_list", "sentiment", "is_recommended", "notes"]  # fmt: skip
    return [HumanLabel(**dict(zip(keys, r, strict=True))) for r in cur.fetchall()]


def load_system_mentions(
    conn: psycopg.Connection, sample_version: str, parser_version: str = "v1"
) -> list[MentionRow]:
    cur = conn.execute(
        """
        SELECT m.response_id::text, m.run_id::text, m.brand_id, m.mentioned, m.mention_count,
               m.first_char_pos, m.rank_in_list, m.is_recommended, m.sentiment, m.snippet,
               m.extraction_method, m.confidence::float AS confidence, m.parser_version
        FROM silver_brand_mentions m
        JOIN validation_samples s ON s.response_id = m.response_id
        WHERE s.sample_version = %s AND m.parser_version = %s
        """,
        (sample_version, parser_version),
    )
    cols = [d.name for d in cur.description]
    return [MentionRow(**dict(zip(cols, r, strict=True))) for r in cur.fetchall()]
