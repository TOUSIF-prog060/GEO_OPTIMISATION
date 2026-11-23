"""Visibility: run diagnostics on a discovery run and see how each brand shows up."""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_settings  # noqa: E402
from src.db import get_conn  # noqa: E402
from src.diagnostics import (  # noqa: E402
    AccuracyInput,
    ClassifyInput,
    DiagnoseInput,
    check_accuracy,
    classify_mentions,
    diagnose,
)
from src.diagnostics.repository import (  # noqa: E402
    PostgresDiagnosticsRepository,
    list_runs,
    load_gold_accuracy,
    load_product_mention_counts,
    load_repeatability,
    load_source_share,
    load_visibility,
    sync_reference,
)

st.set_page_config(page_title="Visibility", layout="wide")
st.title("2 · Visibility")
st.caption(
    "Three separate dimensions: **visibility** (is the brand present?), **accuracy** "
    "(are stated facts correct?) and **sources** (what evidence is cited?)."
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
    st.info("No discovery runs yet. Start one on the Discovery page.")
    st.stop()

labels = {
    r["run_id"]: f"{r['started_at']:%Y-%m-%d %H:%M} · {r['provider']} · {r['panel_version']} "
    f"· {r['status']}"
    for r in runs
}
run_id = st.selectbox("Discovery run", list(labels), format_func=labels.get)

c1, c2, c3 = st.columns(3)
if c1.button("Run diagnostics", type="primary", help="Parse answers and compute metrics. Free."):
    try:
        with get_conn() as conn:
            sync_reference(conn, "v1")
            out = diagnose(DiagnoseInput(run_id=run_id), PostgresDiagnosticsRepository(conn))
        st.success(
            f"Parsed {out.n_responses} answers · {out.n_citations} citations · "
            f"{out.n_mentions} brand mentions · {out.n_product_mentions} product mentions · "
            f"{out.n_skipped_errors} errored calls skipped"
        )
    except Exception as exc:
        st.error(f"Diagnostics failed: {exc}")

no_key = not settings.openai_api_key
if c2.button(
    "Label sentiment (LLM)",
    disabled=no_key,
    help="OPENAI_API_KEY not set" if no_key else "Billed: one small call per brand mention",
):
    bar = st.progress(0.0)
    try:
        with get_conn() as conn:
            res = classify_mentions(
                ClassifyInput(run_id=run_id),
                settings,
                PostgresDiagnosticsRepository(conn),
                on_progress=lambda d, n: bar.progress(d / n, text=f"{d}/{n}"),
            )
        st.success(f"Labelled {res.n_classified} mentions ({res.n_failed} failed)")
    except Exception as exc:
        st.error(f"Labelling failed: {exc}")

if c3.button(
    "Check accuracy (LLM)",
    disabled=no_key,
    help="OPENAI_API_KEY not set"
    if no_key
    else "Billed: one call per answer that mentions a subject with verified facts",
):
    bar = st.progress(0.0)
    try:
        with get_conn() as conn:
            acc = check_accuracy(
                AccuracyInput(run_id=run_id),
                settings,
                PostgresDiagnosticsRepository(conn),
                on_progress=lambda d, n: bar.progress(d / n, text=f"{d}/{n}"),
            )
        st.success(f"{acc.n_checks} fact checks on {acc.n_responses_checked} answers")
    except Exception as exc:
        st.error(f"Accuracy check failed: {exc}")

with get_conn() as conn:
    vis = pd.DataFrame(load_visibility(conn, run_id))
    src = pd.DataFrame(load_source_share(conn, run_id))
    rep_df = pd.DataFrame(load_repeatability(conn, run_id))
    acc_df = pd.DataFrame(load_gold_accuracy(conn, run_id))
    prod_df = pd.DataFrame(load_product_mention_counts(conn, run_id))

if vis.empty:
    st.info("No metrics for this run yet. Click **Run diagnostics**.")
    st.stop()

num = ["mention_rate", "share_of_voice", "avg_rank", "citation_share", "positive_rate"]
vis[num] = vis[num].astype(float)
overall = vis[vis["category"] == "ALL"]
target = overall[overall["is_target"]]

st.subheader("Overall")
if not target.empty:
    t = target.iloc[0]
    k = st.columns(4)
    k[0].metric(f"{t['brand']} mention rate", f"{t['mention_rate']:.0%}")
    k[1].metric(
        "Share of voice", "-" if pd.isna(t["share_of_voice"]) else f"{t['share_of_voice']:.0%}"
    )
    k[2].metric("Avg rank in lists", "-" if pd.isna(t["avg_rank"]) else f"{t['avg_rank']:.1f}")
    k[3].metric(
        "Citation share", "-" if pd.isna(t["citation_share"]) else f"{t['citation_share']:.0%}"
    )

g1, g2 = st.columns(2)
g1.plotly_chart(
    px.bar(
        overall, x="brand", y="mention_rate", title="Mention rate", text_auto=".0%"
    ).update_yaxes(tickformat=".0%"),
    width="stretch",
)
g2.plotly_chart(
    px.pie(overall, names="brand", values="share_of_voice", title="Share of voice", hole=0.5),
    width="stretch",
)

st.subheader("By category")
by_cat = vis[vis["category"] != "ALL"]
st.plotly_chart(
    px.bar(
        by_cat,
        x="category",
        y="mention_rate",
        color="brand",
        barmode="group",
        title="Mention rate by category",
    ).update_yaxes(tickformat=".0%"),
    width="stretch",
)

if not src.empty:
    st.subheader("Who gets cited")
    s_all = src[src["category"] == "ALL"].copy()
    s_all["citation_share"] = s_all["citation_share"].astype(float)
    h1, h2 = st.columns(2)
    h1.plotly_chart(
        px.pie(
            s_all.groupby("domain_type", as_index=False)["n_citations"].sum(),
            names="domain_type",
            values="n_citations",
            title="Citations by source type",
        ),
        width="stretch",
    )
    h2.plotly_chart(
        px.bar(
            s_all.head(15),
            x="n_citations",
            y="domain",
            color="domain_type",
            orientation="h",
            title="Top cited domains",
        ).update_yaxes(autorange="reversed"),
        width="stretch",
    )
    unclassified = s_all[s_all["domain_type"] == "unclassified"]["domain"].tolist()
    if unclassified:
        with st.expander(f"{len(unclassified)} unclassified domains (add to domains_v1.csv)"):
            st.write(", ".join(unclassified))

st.subheader("Repeatability")
if rep_df.empty:
    st.caption("Run discovery with 2+ repeats per prompt to measure how stable answers are.")
else:
    rep_df["agreement_rate"] = rep_df["agreement_rate"].astype(float)
    st.caption(
        "Agreement = share of repeated prompts where every repeat agreed on whether the brand "
        "was mentioned. Low agreement means single answers are unreliable."
    )
    st.dataframe(rep_df, width="stretch", hide_index=True)

st.subheader("Accuracy")
if acc_df.empty:
    st.caption(
        "No accuracy checks yet. Fill data/reference/reference_facts_v1.csv with verified "
        "facts, run diagnostics, then **Check accuracy**."
    )
else:
    st.caption("Accuracy rate = match / (match + mismatch). Not-stated facts are listed apart.")
    st.dataframe(acc_df, width="stretch", hide_index=True)

st.subheader("Products mentioned")
if prod_df.empty:
    st.caption("No catalogue products found. Fill data/reference/products_v1.csv to track them.")
else:
    st.dataframe(prod_df, width="stretch", hide_index=True)

with st.expander("All metrics"):
    st.dataframe(vis, width="stretch", hide_index=True)
