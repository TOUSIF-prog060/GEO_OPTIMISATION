"""Content Copilot: grounded drafts from approved brand knowledge, with human review."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_settings  # noqa: E402
from src.copilot import DraftInput, draft_content, ingest_knowledge  # noqa: E402
from src.copilot.knowledge import load_docs  # noqa: E402
from src.copilot.repository import (  # noqa: E402
    PostgresCopilotRepository,
    kb_stats,
    list_variants,
    load_chunks,
    review_variant,
)
from src.db import get_conn  # noqa: E402
from src.opportunities.repository import list_opportunities  # noqa: E402

st.set_page_config(page_title="Copilot", layout="wide")
st.title("5 · Content Copilot")
st.caption(
    "Drafts are written only from approved brand documents (RAG) and must cite them. "
    "Every draft is checked for grounding and waits for human approval."
)

settings = get_settings()
if not settings.supabase_db_url:
    st.warning("SUPABASE_DB_URL is not set in .env. Connect the database to use this page.")
    st.stop()
no_key = not settings.openai_api_key

# ---------------------------------------------------------------- knowledge base
st.subheader("Knowledge base")
try:
    local_docs = load_docs()
    doc_error = None
except ValueError as exc:
    local_docs, doc_error = [], str(exc)
try:
    with get_conn() as conn:
        stats = kb_stats(conn)
except Exception as exc:
    st.error(f"Database error: {exc}")
    st.stop()
c = st.columns(3)
c[0].metric("Approved docs in folder", len(local_docs))
c[1].metric("Docs in database", stats["documents"])
c[2].metric("Chunks embedded", stats["chunks"])
if doc_error:
    st.error(doc_error)
st.caption("Add approved Markdown files to `data/knowledge/` (see its README).")
if st.button("Ingest / refresh", disabled=no_key or not local_docs,
             help="OPENAI_API_KEY not set" if no_key else "Embeds new/changed docs"):  # fmt: skip
    try:
        with get_conn() as conn:
            out = ingest_knowledge(settings, PostgresCopilotRepository(conn))
        st.success(f"{out.n_chunks} chunks embedded · {out.n_skipped_unchanged} docs unchanged")
    except Exception as exc:
        st.error(f"Ingestion failed: {exc}")

# ---------------------------------------------------------------- draft
st.subheader("Draft content for an opportunity")
with get_conn() as conn:
    opps = list_opportunities(conn)
if not opps:
    st.info("No opportunities yet. Create them on the Opportunities page.")
else:
    labels = {
        o["opportunity_id"]: f"[{o['priority_score']:.0f}] {o['title']} · {o['rec_status']}"
        for o in opps
    }
    opp_id = st.selectbox("Opportunity", list(labels), format_func=labels.get)
    only_approved = st.checkbox("Only if the recommendation is approved", value=True)
    if st.button("Generate draft", type="primary", disabled=no_key or stats["chunks"] == 0,
                 help="Billed: 1 embedding + 1 generation call"):  # fmt: skip
        try:
            with get_conn() as conn:
                out = draft_content(
                    DraftInput(
                        opportunity_id=opp_id, require_approved_recommendation=only_approved
                    ),
                    settings,
                    PostgresCopilotRepository(conn),
                )
            msg = f"Draft v{out.version} saved · grounded: {out.grounded}"
            (st.success if out.grounded else st.warning)(msg)
        except Exception as exc:
            st.error(f"Drafting failed: {exc}")

# ---------------------------------------------------------------- review
st.subheader("Review drafts")
with get_conn() as conn:
    variants = list_variants(conn)
if not variants:
    st.caption("No drafts yet.")
    st.stop()
reviewer = st.text_input("Your initials", max_chars=8)
for v in variants:
    icon = {"approved": "✅", "rejected": "❌"}.get(v["status"], "📝")
    flag = "" if v["grounded"] else " ⚠️ not fully grounded"
    with st.expander(f"{icon} v{v['version']} · {v['title']} ({v['content_type']}){flag}"):
        st.caption(f"Opportunity: {v['opportunity']} · by {v['generated_by']}")
        g = v["grounding"] or {}
        if g.get("invalid_citations"):
            st.error(f"Cites chunks that were not retrieved: {g['invalid_citations']}")
        if g.get("unsupported_claims"):
            st.warning("Claims the model could not support: " + "; ".join(g["unsupported_claims"]))
        if g.get("needs_more_info"):
            st.warning("The model says the sources are not enough. Add more approved docs.")
        st.markdown(v["body"])
        if g.get("cited_chunk_ids") and st.checkbox("Show sources", key=f"s-{v['variant_id']}"):
            with get_conn() as conn:
                st.dataframe(pd.DataFrame(load_chunks(conn, g["cited_chunk_ids"])), hide_index=True)
        notes = st.text_input("Review notes", key=f"n-{v['variant_id']}")
        b1, b2 = st.columns(2)
        if b1.button("Approve", key=f"a-{v['variant_id']}", disabled=not reviewer):
            with get_conn() as conn:
                review_variant(conn, v["variant_id"], "approved", reviewer, notes)
            st.rerun()
        if b2.button("Reject", key=f"r-{v['variant_id']}", disabled=not reviewer):
            with get_conn() as conn:
                review_variant(conn, v["variant_id"], "rejected", reviewer, notes)
            st.rerun()
