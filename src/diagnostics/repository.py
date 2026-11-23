"""Database access for diagnostics. The engine depends on the `DiagnosticsRepository`
protocol, so tests use an in-memory fake instead of Postgres."""

from __future__ import annotations

import logging
from typing import Any, Protocol

import psycopg

from src.diagnostics.models import (
    AccuracyCheckRow,
    AccuracyRow,
    BrandRef,
    CitationRow,
    DomainRef,
    FactRef,
    MentionLabel,
    MentionRow,
    MentionToLabel,
    ProductMentionRow,
    ProductRef,
    RepeatabilityRow,
    ResponseRecord,
    SourceShareRow,
    VisibilityRow,
)
from src.diagnostics.reference import DomainCsvRow, FactCsvRow, ProductCsvRow

logger = logging.getLogger(__name__)


class DiagnosticsRepository(Protocol):
    def load_responses(self, run_id: str) -> list[ResponseRecord]: ...
    def load_brands(self) -> list[BrandRef]: ...
    def load_domains(self) -> dict[str, DomainRef]: ...
    def save_silver(self, citations: list[CitationRow], mentions: list[MentionRow]) -> None: ...
    def load_mentions(self, run_id: str, parser_version: str) -> list[MentionRow]: ...
    def load_citations(self, run_id: str, parser_version: str) -> list[CitationRow]: ...
    def save_gold(self, visibility: list[VisibilityRow], sources: list[SourceShareRow]) -> None: ...
    def load_unlabelled(self, run_id: str, parser_version: str) -> list[MentionToLabel]: ...
    def save_label(self, mention_id: int, label: MentionLabel, classified_by: str) -> None: ...
    def load_products(self) -> list[ProductRef]: ...
    def load_facts(self) -> dict[str, FactRef]: ...
    def save_product_mentions(self, rows: list[ProductMentionRow]) -> None: ...
    def load_product_mentions(
        self, run_id: str, parser_version: str
    ) -> list[ProductMentionRow]: ...
    def save_repeatability(self, rows: list[RepeatabilityRow]) -> None: ...
    def save_accuracy(self, checks: list[AccuracyCheckRow]) -> None: ...
    def load_accuracy_checks(self, run_id: str, checker_version: str) -> list[AccuracyCheckRow]: ...
    def save_gold_accuracy(self, rows: list[AccuracyRow]) -> None: ...


class PostgresDiagnosticsRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    # ------------------------------------------------------------ reads
    def load_responses(self, run_id: str) -> list[ResponseRecord]:
        cur = self.conn.execute(
            """
            SELECT b.response_id::text, b.run_id::text, b.prompt_id, b.provider, p.category,
                   b.repeat_no, p.text, b.answer_text, b.raw_response, b.error
            FROM bronze_responses b JOIN prompts p USING (prompt_id)
            WHERE b.run_id = %s
            """,
            (run_id,),
        )
        keys = [
            "response_id", "run_id", "prompt_id", "provider", "category", "repeat_no",
            "prompt_text", "answer_text", "raw_response", "error",
        ]  # fmt: skip
        return [ResponseRecord(**dict(zip(keys, r, strict=True))) for r in cur.fetchall()]

    def load_brands(self) -> list[BrandRef]:
        cur = self.conn.execute(
            "SELECT brand_id, name, aliases, is_target FROM brands ORDER BY brand_id"
        )
        return [BrandRef(brand_id=r[0], name=r[1], aliases=r[2], is_target=r[3]) for r in cur]

    def load_domains(self) -> dict[str, DomainRef]:
        cur = self.conn.execute("SELECT domain, domain_type, brand_id FROM domains")
        return {r[0]: DomainRef(domain=r[0], domain_type=r[1], brand_id=r[2]) for r in cur}

    def load_mentions(self, run_id: str, parser_version: str) -> list[MentionRow]:
        cur = self.conn.execute(
            """
            SELECT response_id::text, run_id::text, brand_id, mentioned, mention_count,
                   first_char_pos, rank_in_list, is_recommended, sentiment, snippet,
                   extraction_method, confidence::float, parser_version
            FROM silver_brand_mentions WHERE run_id = %s AND parser_version = %s
            """,
            (run_id, parser_version),
        )
        cols = [d.name for d in cur.description]
        return [MentionRow(**dict(zip(cols, r, strict=True))) for r in cur.fetchall()]

    def load_citations(self, run_id: str, parser_version: str) -> list[CitationRow]:
        cur = self.conn.execute(
            """
            SELECT response_id::text, run_id::text, position, url, domain, title, parser_version
            FROM silver_citations WHERE run_id = %s AND parser_version = %s
            """,
            (run_id, parser_version),
        )
        cols = [d.name for d in cur.description]
        return [CitationRow(**dict(zip(cols, r, strict=True))) for r in cur.fetchall()]

    def load_unlabelled(self, run_id: str, parser_version: str) -> list[MentionToLabel]:
        cur = self.conn.execute(
            """
            SELECT m.mention_id, br.name, p.text, b.answer_text
            FROM silver_brand_mentions m
            JOIN brands br USING (brand_id)
            JOIN bronze_responses b USING (response_id)
            JOIN prompts p ON p.prompt_id = b.prompt_id
            WHERE m.run_id = %s AND m.parser_version = %s AND m.mentioned AND m.sentiment IS NULL
            """,
            (run_id, parser_version),
        )
        return [
            MentionToLabel(mention_id=r[0], brand_name=r[1], prompt_text=r[2], answer_text=r[3])
            for r in cur
        ]

    # ------------------------------------------------------------ writes
    def save_silver(self, citations: list[CitationRow], mentions: list[MentionRow]) -> None:
        """Idempotent. Re-parsing updates mention facts but keeps existing LLM labels."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO silver_citations
                  (response_id, run_id, position, url, domain, title, parser_version)
                VALUES (%(response_id)s, %(run_id)s, %(position)s, %(url)s, %(domain)s,
                        %(title)s, %(parser_version)s)
                ON CONFLICT (response_id, position, parser_version) DO UPDATE
                SET url = EXCLUDED.url, domain = EXCLUDED.domain, title = EXCLUDED.title
                """,
                [c.model_dump() for c in citations],
            )
            cur.executemany(
                """
                INSERT INTO silver_brand_mentions
                  (response_id, run_id, brand_id, mentioned, mention_count, first_char_pos,
                   rank_in_list, snippet, extraction_method, confidence, parser_version)
                VALUES (%(response_id)s, %(run_id)s, %(brand_id)s, %(mentioned)s,
                        %(mention_count)s, %(first_char_pos)s, %(rank_in_list)s, %(snippet)s,
                        %(extraction_method)s, %(confidence)s, %(parser_version)s)
                ON CONFLICT (response_id, brand_id, parser_version) DO UPDATE
                SET mentioned = EXCLUDED.mentioned, mention_count = EXCLUDED.mention_count,
                    first_char_pos = EXCLUDED.first_char_pos,
                    rank_in_list = EXCLUDED.rank_in_list, snippet = EXCLUDED.snippet,
                    extraction_method = EXCLUDED.extraction_method,
                    confidence = EXCLUDED.confidence
                """,
                [m.model_dump() for m in mentions],
            )
        self.conn.commit()

    def save_gold(self, visibility: list[VisibilityRow], sources: list[SourceShareRow]) -> None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO gold_visibility
                  (run_id, brand_id, category, n_responses, mention_rate, share_of_voice,
                   avg_rank, citation_share, positive_rate, metric_version)
                VALUES (%(run_id)s, %(brand_id)s, %(category)s, %(n_responses)s,
                        %(mention_rate)s, %(share_of_voice)s, %(avg_rank)s,
                        %(citation_share)s, %(positive_rate)s, %(metric_version)s)
                ON CONFLICT (run_id, brand_id, category, metric_version) DO UPDATE
                SET n_responses = EXCLUDED.n_responses, mention_rate = EXCLUDED.mention_rate,
                    share_of_voice = EXCLUDED.share_of_voice, avg_rank = EXCLUDED.avg_rank,
                    citation_share = EXCLUDED.citation_share,
                    positive_rate = EXCLUDED.positive_rate, computed_at = now()
                """,
                [v.model_dump() for v in visibility],
            )
            if sources:
                run_ids = {s.run_id for s in sources}
                versions = {s.metric_version for s in sources}
                cur.execute(  # domains can drop out on re-parse, so replace the run's rows
                    "DELETE FROM gold_source_share WHERE run_id = ANY(%s) "
                    "AND metric_version = ANY(%s)",
                    (list(run_ids), list(versions)),
                )
            cur.executemany(
                """
                INSERT INTO gold_source_share
                  (run_id, category, domain, domain_type, n_citations, citation_share,
                   metric_version)
                VALUES (%(run_id)s, %(category)s, %(domain)s, %(domain_type)s,
                        %(n_citations)s, %(citation_share)s, %(metric_version)s)
                """,
                [s.model_dump() for s in sources],
            )
        self.conn.commit()

    def save_label(self, mention_id: int, label: MentionLabel, classified_by: str) -> None:
        self.conn.execute(
            """
            UPDATE silver_brand_mentions
            SET sentiment = %s, is_recommended = %s, classified_by = %s, classified_at = now()
            WHERE mention_id = %s
            """,
            (label.sentiment, label.is_recommended, classified_by, mention_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------ charter additions
    def load_products(self) -> list[ProductRef]:
        cur = self.conn.execute(
            "SELECT product_id, product_name, maker, aliases, category FROM products"
        )
        return [
            ProductRef(product_id=r[0], product_name=r[1], maker=r[2], aliases=r[3], category=r[4])
            for r in cur
        ]

    def load_facts(self) -> dict[str, FactRef]:
        cur = self.conn.execute(
            """
            SELECT fact_id, subject_type, subject, attribute, approved_value, value_type,
                   tolerance::float AS tolerance
            FROM reference_facts
            """
        )
        cols = [d.name for d in cur.description]
        return {r[0]: FactRef(**dict(zip(cols, r, strict=True))) for r in cur.fetchall()}

    def save_product_mentions(self, rows: list[ProductMentionRow]) -> None:
        if not rows:
            return
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO silver_product_mentions
                  (response_id, run_id, product_id, mention_count, first_char_pos, rank_in_list,
                   snippet, extraction_method, confidence, parser_version)
                VALUES (%(response_id)s, %(run_id)s, %(product_id)s, %(mention_count)s,
                        %(first_char_pos)s, %(rank_in_list)s, %(snippet)s,
                        %(extraction_method)s, %(confidence)s, %(parser_version)s)
                ON CONFLICT (response_id, product_id, parser_version) DO UPDATE
                SET mention_count = EXCLUDED.mention_count,
                    first_char_pos = EXCLUDED.first_char_pos,
                    rank_in_list = EXCLUDED.rank_in_list, snippet = EXCLUDED.snippet
                """,
                [r.model_dump() for r in rows],
            )
        self.conn.commit()

    def load_product_mentions(self, run_id: str, parser_version: str) -> list[ProductMentionRow]:
        cur = self.conn.execute(
            """
            SELECT response_id::text, run_id::text, product_id, mention_count, first_char_pos,
                   rank_in_list, snippet, extraction_method, confidence::float AS confidence,
                   parser_version
            FROM silver_product_mentions WHERE run_id = %s AND parser_version = %s
            """,
            (run_id, parser_version),
        )
        cols = [d.name for d in cur.description]
        return [ProductMentionRow(**dict(zip(cols, r, strict=True))) for r in cur.fetchall()]

    def save_repeatability(self, rows: list[RepeatabilityRow]) -> None:
        if not rows:
            return
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO gold_repeatability
                  (run_id, brand_id, n_prompts, agreement_rate, mean_within_prompt_sd,
                   metric_version)
                VALUES (%(run_id)s, %(brand_id)s, %(n_prompts)s, %(agreement_rate)s,
                        %(mean_within_prompt_sd)s, %(metric_version)s)
                ON CONFLICT (run_id, brand_id, metric_version) DO UPDATE
                SET n_prompts = EXCLUDED.n_prompts, agreement_rate = EXCLUDED.agreement_rate,
                    mean_within_prompt_sd = EXCLUDED.mean_within_prompt_sd, computed_at = now()
                """,
                [r.model_dump() for r in rows],
            )
        self.conn.commit()

    def save_accuracy(self, checks: list[AccuracyCheckRow]) -> None:
        if not checks:
            return
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO silver_accuracy_checks
                  (response_id, run_id, fact_id, stated_value, approved_value, verdict,
                   extraction_method, extracted_by, checker_version)
                VALUES (%(response_id)s, %(run_id)s, %(fact_id)s, %(stated_value)s,
                        %(approved_value)s, %(verdict)s, %(extraction_method)s,
                        %(extracted_by)s, %(checker_version)s)
                ON CONFLICT (response_id, fact_id, checker_version) DO UPDATE
                SET stated_value = EXCLUDED.stated_value,
                    approved_value = EXCLUDED.approved_value, verdict = EXCLUDED.verdict,
                    extracted_by = EXCLUDED.extracted_by, created_at = now()
                """,
                [c.model_dump() for c in checks],
            )
        self.conn.commit()

    def load_accuracy_checks(self, run_id: str, checker_version: str) -> list[AccuracyCheckRow]:
        cur = self.conn.execute(
            """
            SELECT response_id::text, run_id::text, fact_id, stated_value, approved_value,
                   verdict, extraction_method, extracted_by, checker_version
            FROM silver_accuracy_checks WHERE run_id = %s AND checker_version = %s
            """,
            (run_id, checker_version),
        )
        cols = [d.name for d in cur.description]
        return [AccuracyCheckRow(**dict(zip(cols, r, strict=True))) for r in cur.fetchall()]

    def save_gold_accuracy(self, rows: list[AccuracyRow]) -> None:
        if not rows:
            return
        with self.conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO gold_accuracy
                  (run_id, subject, attribute, n_checked, n_match, n_mismatch, n_not_mentioned,
                   n_unverifiable, accuracy_rate, metric_version)
                VALUES (%(run_id)s, %(subject)s, %(attribute)s, %(n_checked)s, %(n_match)s,
                        %(n_mismatch)s, %(n_not_mentioned)s, %(n_unverifiable)s,
                        %(accuracy_rate)s, %(metric_version)s)
                ON CONFLICT (run_id, subject, attribute, metric_version) DO UPDATE
                SET n_checked = EXCLUDED.n_checked, n_match = EXCLUDED.n_match,
                    n_mismatch = EXCLUDED.n_mismatch, n_not_mentioned = EXCLUDED.n_not_mentioned,
                    n_unverifiable = EXCLUDED.n_unverifiable,
                    accuracy_rate = EXCLUDED.accuracy_rate, computed_at = now()
                """,
                [r.model_dump() for r in rows],
            )
        self.conn.commit()


def sync_domains(conn: psycopg.Connection, rows: list[DomainCsvRow], ref_version: str) -> int:
    """Upsert domain reference rows. brand_name is resolved to brand_id (brands must exist)."""
    brand_ids = {name: bid for bid, name in conn.execute("SELECT brand_id, name FROM brands")}
    missing = {r.brand_name for r in rows if r.brand_name and r.brand_name not in brand_ids}
    if missing:
        raise ValueError(f"Brands not in DB (run discovery sync first): {sorted(missing)}")
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO domains (domain, domain_type, brand_id, ref_version)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (domain) DO UPDATE
            SET domain_type = EXCLUDED.domain_type, brand_id = EXCLUDED.brand_id,
                ref_version = EXCLUDED.ref_version
            """,
            [
                (r.domain, r.domain_type, brand_ids.get(r.brand_name or ""), ref_version)
                for r in rows
            ],
        )
    conn.commit()
    logger.info("Synced %d domains (%s)", len(rows), ref_version)
    return len(rows)


def list_runs(conn: psycopg.Connection, limit: int = 50) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT run_id::text, provider, model, panel_version, status, started_at
        FROM bronze_runs ORDER BY started_at DESC LIMIT %s
        """,
        (limit,),
    )
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def load_visibility(conn: psycopg.Connection, run_id: str, metric_version: str = "v1"):
    cur = conn.execute(
        """
        SELECT b.name AS brand, b.is_target, g.category, g.n_responses, g.mention_rate,
               g.share_of_voice, g.avg_rank, g.citation_share, g.positive_rate
        FROM gold_visibility g JOIN brands b USING (brand_id)
        WHERE g.run_id = %s AND g.metric_version = %s
        ORDER BY g.category, b.is_target DESC, b.name
        """,
        (run_id, metric_version),
    )
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def load_source_share(conn: psycopg.Connection, run_id: str, metric_version: str = "v1"):
    cur = conn.execute(
        """
        SELECT category, domain, domain_type, n_citations, citation_share
        FROM gold_source_share WHERE run_id = %s AND metric_version = %s
        ORDER BY category, n_citations DESC
        """,
        (run_id, metric_version),
    )
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def sync_products(conn: psycopg.Connection, rows: list[ProductCsvRow], ref_version: str) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO products (product_id, product_name, maker, aliases, category, source_url,
                                  last_verified_at, ref_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (product_id) DO UPDATE
            SET product_name = EXCLUDED.product_name, maker = EXCLUDED.maker,
                aliases = EXCLUDED.aliases, category = EXCLUDED.category,
                source_url = EXCLUDED.source_url, last_verified_at = EXCLUDED.last_verified_at,
                ref_version = EXCLUDED.ref_version
            """,
            [
                (
                    r.product_id,
                    r.product_name,
                    r.maker,
                    r.aliases,
                    r.category,
                    r.source_url,
                    r.last_verified_at,
                    ref_version,
                )
                for r in rows
            ],  # fmt: skip
        )
    conn.commit()
    return len(rows)


def sync_facts(conn: psycopg.Connection, rows: list[FactCsvRow], ref_version: str) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO reference_facts (fact_id, subject_type, subject, attribute, approved_value,
                                         value_type, tolerance, source_url, last_verified_at,
                                         ref_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (fact_id) DO UPDATE
            SET approved_value = EXCLUDED.approved_value, value_type = EXCLUDED.value_type,
                tolerance = EXCLUDED.tolerance, source_url = EXCLUDED.source_url,
                last_verified_at = EXCLUDED.last_verified_at, ref_version = EXCLUDED.ref_version
            """,
            [
                (
                    r.fact_id,
                    r.subject_type,
                    r.subject,
                    r.attribute,
                    r.approved_value,
                    r.value_type,
                    r.tolerance,
                    r.source_url,
                    r.last_verified_at,
                    ref_version,
                )
                for r in rows
            ],  # fmt: skip
        )
    conn.commit()
    return len(rows)


def _rows(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def load_repeatability(conn: psycopg.Connection, run_id: str, metric_version: str = "v1"):
    return _rows(
        conn.execute(
            """
            SELECT b.name AS brand, g.n_prompts, g.agreement_rate, g.mean_within_prompt_sd
            FROM gold_repeatability g JOIN brands b USING (brand_id)
            WHERE g.run_id = %s AND g.metric_version = %s ORDER BY b.is_target DESC, b.name
            """,
            (run_id, metric_version),
        )
    )


def load_gold_accuracy(conn: psycopg.Connection, run_id: str, metric_version: str = "v1"):
    return _rows(
        conn.execute(
            """
            SELECT subject, attribute, n_checked, n_match, n_mismatch, n_not_mentioned,
                   n_unverifiable, accuracy_rate
            FROM gold_accuracy WHERE run_id = %s AND metric_version = %s
            ORDER BY subject, attribute
            """,
            (run_id, metric_version),
        )
    )


def load_product_mention_counts(conn: psycopg.Connection, run_id: str, parser_version: str = "v1"):
    return _rows(
        conn.execute(
            """
            SELECT p.product_name, p.maker, p.category, count(*) AS n_responses,
                   avg(m.rank_in_list)::float AS avg_rank
            FROM silver_product_mentions m JOIN products p USING (product_id)
            WHERE m.run_id = %s AND m.parser_version = %s
            GROUP BY p.product_name, p.maker, p.category ORDER BY n_responses DESC
            """,
            (run_id, parser_version),
        )
    )


def sync_reference(conn: psycopg.Connection, version: str = "v1") -> dict[str, int]:
    """Load domains, products and verified facts (all `<name>_<version>.csv`) into the DB.
    Brands must already be synced (discovery does this)."""
    from src.diagnostics.reference import (
        domains_path,
        facts_path,
        load_domains_csv,
        load_facts_csv,
        load_products_csv,
        products_path,
    )

    brand_names = {r[0] for r in conn.execute("SELECT name FROM brands")}
    products = load_products_csv(products_path(version))
    facts = load_facts_csv(facts_path(version), brand_names, {p.product_id for p in products})
    return {
        "domains": sync_domains(conn, load_domains_csv(domains_path(version)), version),
        "products": sync_products(conn, products, version),
        "facts": sync_facts(conn, facts, version),
    }
