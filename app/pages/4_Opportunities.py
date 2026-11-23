"""Opportunities: ranked, evidence-linked gaps with recommendations for human review."""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_settings  # noqa: E402
from src.db import get_conn  # noqa: E402
from src.diagnostics.repository import list_runs  # noqa: E402
from src.opportunities import OpportunityInput, find_opportunities  # noqa: E402
from src.opportunities.repository import (  # noqa: E402
    PostgresOpportunityRepository,
    list_opportunities,
    load_evidence,
    review_recommendation,
)

st.set_page_config(page_title="Opportunities", layout="wide")
st.title("4 · Opportunities")
st.caption(
    "Gaps found in the diagnostics, ranked by priority = severity × confidence ÷ effort. "
    "Each links to the AI answers that show it. Observations on this prompt sample only."
)

settings = get_settings()
if not settings.supabase_db_url:
    st.warning("SUPABASE_DB_URL is not set in .env. Connect the database to use this page.")
    st.stop()

try:
    with get_conn() as conn:
        runs = list_runs(conn)
except Exception as exc:
    st.error(f"Database error: {exc}")
    st.stop()
if not runs:
    st.info("No discovery runs yet.")
    st.stop()

labels = {
    r["run_id"]: f"{r['started_at']:%Y-%m-%d %H:%M} · {r['provider']} · {r['status']}" for r in runs
}
run_id = st.selectbox("Diagnosed run", list(labels), format_func=labels.get)

if st.button("Find opportunities", type="primary", help="Rule-based, free. Run diagnostics first."):
    try:
        with get_conn() as conn:
            out = find_opportunities(
                OpportunityInput(run_id=run_id), PostgresOpportunityRepository(conn)
            )
        st.success(f"{out.n_opportunities} opportunities found: {out.by_type}")
    except Exception as exc:
        st.error(f"Failed: {exc}")

with get_conn() as conn:
    df = pd.DataFrame(list_opportunities(conn, run_id))
if df.empty:
    st.info("No opportunities for this run yet.")
    st.stop()

k = st.columns(4)
k[0].metric("Opportunities", len(df))
k[1].metric("Awaiting review", int((df["rec_status"] == "proposed").sum()))
k[2].metric("Approved", int((df["rec_status"] == "approved").sum()))
k[3].metric("Top priority", f"{df['priority_score'].max():.1f}")

st.plotly_chart(
    px.scatter(
        df, x="confidence", y="severity", size="n_evidence", color="gap_type",
        hover_name="title", size_max=40, title="Severity vs confidence (bubble = evidence answers)",
    ).update_layout(xaxis_range=[0, 1.05], yaxis_range=[0, 1.05]),
    width="stretch",
)  # fmt: skip

reviewer = st.text_input("Your initials (recorded on approvals)", max_chars=8)
for _, o in df.iterrows():
    badge = {"approved": "✅", "rejected": "❌"}.get(o["rec_status"], "🕒")
    with st.expander(f"{badge} [{o['priority_score']:.1f}] {o['title']}"):
        c = st.columns(4)
        c[0].metric("Severity", f"{o['severity']:.2f}")
        c[1].metric("Confidence", f"{o['confidence']:.2f}")
        c[2].metric("Effort", o["effort"])
        c[3].metric("Evidence answers", int(o["n_evidence"]))
        st.markdown(f"**Why:** {o['rationale']}")
        st.markdown(f"**Recommended action:** {o['action']}")
        st.markdown(f"**How to validate:** {o['validation_approach']}")
        if o["review_notes"]:
            st.caption(f"Review notes ({o['reviewed_by']}): {o['review_notes']}")
        if st.checkbox("Show evidence", key=f"ev-{o['opportunity_id']}"):
            with get_conn() as conn:
                st.dataframe(
                    pd.DataFrame(load_evidence(conn, o["opportunity_id"])), hide_index=True
                )
        notes = st.text_input("Notes", key=f"n-{o['opportunity_id']}")
        b1, b2 = st.columns(2)
        for col, status in ((b1, "approved"), (b2, "rejected")):
            label = "Approve" if status == "approved" else "Reject"
            key = f"{status}-{o['opportunity_id']}"
            if col.button(label, key=key, disabled=not reviewer):
                with get_conn() as conn:
                    review_recommendation(conn, o["recommendation_id"], status, reviewer, notes)
                st.rerun()
