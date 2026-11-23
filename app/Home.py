"""Beyond the Search Bar: overview dashboard. Run: streamlit run app/Home.py"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings  # noqa: E402
from src.db import check_connection, get_conn  # noqa: E402
from src.reporting import (  # noqa: E402
    category_matrix,
    kpi_deltas,
    leader_by_provider,
    ops_stats,
    pipeline_counts,
    top_opportunities,
    visibility_history,
)

st.set_page_config(page_title="Beyond the Search Bar", page_icon="🔍", layout="wide")
st.title("🔍 Beyond the Search Bar")
st.caption("AI Discovery Intelligence Platform (GEO) · pilot: beauty & skincare, India")

settings = get_settings()
project = settings.project

# ---------------------------------------------------------------- system status
with st.expander("System status", expanded=not settings.supabase_db_url):
    cols = st.columns(len(project.providers) + 2)
    db_ok = False
    if not settings.supabase_db_url:
        cols[0].error("DB not configured: set SUPABASE_DB_URL in .env")
    else:
        db_ok, message = check_connection(settings.supabase_db_url)
        (cols[0].success if db_ok else cols[0].error)("DB connected" if db_ok else "DB failed")
        if not db_ok:
            st.code(message)
    for col, p in zip(cols[1:], project.providers, strict=False):
        has_key = bool(getattr(settings, f"{p.name}_api_key", None))
        col.metric(p.name, p.model, "key set" if has_key else "no key", delta_color="off")
    key_note = "key set" if settings.openai_api_key else "no key"
    cols[-1].metric("analysis LLM", project.analysis.model, key_note, delta_color="off")
    competitors = ", ".join(b.name for b in project.competitors)
    st.write(
        f"**Target:** {project.target.name} · **Competitors:** {competitors} · "
        f"**Market:** {project.market}"
    )

if not db_ok:
    st.info(
        "Connect the database to see the dashboard. Workflow: **1 Discovery → 2 Visibility → "
        "3 Validation → 4 Opportunities → 5 Copilot → 6 Agent → 7 Experiments** (sidebar)."
    )
    st.stop()

with get_conn() as conn:
    counts = pipeline_counts(conn)
    try:
        history = visibility_history(conn)
        matrix = category_matrix(conn)
        ops = ops_stats(conn)
        top = top_opportunities(conn)
    except Exception as exc:
        st.error(f"Could not load dashboard data (have all migrations been applied?): {exc}")
        st.stop()

if any(v == -1 for v in counts.values()):
    st.warning("Some tables are missing. Apply all migrations: `python -m src.db`.")

# ---------------------------------------------------------------- workflow progress
st.subheader("Workflow")
steps = [
    ("Runs", counts["runs"]), ("Answers", counts["answers"]),
    ("Opportunities", counts["opportunities"]), ("Recs approved", counts["recs_approved"]),
    ("Drafts", counts["drafts"]), ("Drafts approved", counts["drafts_approved"]),
    ("Experiments done", counts["experiments_done"]), ("Knowledge chunks", counts["kb_chunks"]),
]  # fmt: skip
for col, (label, n) in zip(st.columns(len(steps)), steps, strict=True):
    col.metric(label, "–" if n == -1 else n)

if not history:
    st.info(
        "No diagnosed runs yet. Start on **1 Discovery**, then **2 Visibility → Run diagnostics**."
    )
    st.stop()

hist = pd.DataFrame(history)

# ---------------------------------------------------------------- headline KPIs
st.subheader(f"{project.target.name}: latest visibility")
kpis = kpi_deltas(history)
leaders = leader_by_provider(history)
for col, k in zip(st.columns(max(1, len(kpis))), kpis, strict=False):
    col.metric(
        f"Mention rate · {k['provider']}",
        "–" if k["value"] is None else f"{k['value']:.0%}",
        None if k["delta"] is None else f"{k['delta']:+.0%} vs previous run",
        help=f"n = {k['n_responses']} answers. "
        f"Leader on this provider: {leaders.get(k['provider'])}",
    )
latest = hist.sort_values("started_at").groupby(["provider", "brand"], as_index=False).last()
c1, c2 = st.columns(2)
c1.plotly_chart(
    px.bar(latest, x="brand", y="mention_rate", color="provider", barmode="group",
           text_auto=".0%", title="Mention rate by provider (latest run)")
    .update_yaxes(tickformat=".0%"),
    width="stretch",
)  # fmt: skip
c2.plotly_chart(
    px.bar(latest, x="brand", y="share_of_voice", color="provider", barmode="group",
           text_auto=".0%", title="Share of voice (latest run)").update_yaxes(tickformat=".0%"),
    width="stretch",
)  # fmt: skip

# ---------------------------------------------------------------- trend
if hist["run_id"].nunique() > 1:
    st.plotly_chart(
        px.line(hist, x="started_at", y="mention_rate", color="brand", line_dash="provider",
                markers=True, title="Mention rate over time").update_yaxes(tickformat=".0%"),
        width="stretch",
    )  # fmt: skip

# ---------------------------------------------------------------- category heatmap
if matrix:
    m = pd.DataFrame(matrix)
    m["column"] = m["brand"] + " · " + m["provider"]
    pivot = m.pivot_table(index="category", columns="column", values="mention_rate")
    st.plotly_chart(
        px.imshow(pivot, text_auto=".0%", aspect="auto", color_continuous_scale="Purples",
                  title="Mention rate by category (latest run per provider)"),
        width="stretch",
    )  # fmt: skip

# ---------------------------------------------------------------- opportunities + ops
c1, c2 = st.columns(2)
with c1:
    st.subheader("Top opportunities")
    if top:
        st.dataframe(pd.DataFrame(top), width="stretch", hide_index=True)
    else:
        st.caption("None yet: see **4 Opportunities**.")
with c2:
    st.subheader("Operations")
    o = pd.DataFrame(ops)
    if not o.empty:
        k = st.columns(3)
        k[0].metric("API spend (est.)", f"${o['cost_usd'].fillna(0).sum():.2f}")
        k[1].metric("Error rate", f"{o['errors'].sum() / max(1, o['calls'].sum()):.1%}")
        k[2].metric("Avg latency", f"{o['avg_latency_ms'].mean() / 1000:.1f}s"
                    if o["avg_latency_ms"].notna().any() else "–")  # fmt: skip
        st.dataframe(o[["provider", "run_type", "status", "calls", "errors", "cost_usd"]],
                     width="stretch", hide_index=True)  # fmt: skip

st.caption(
    "Scope: metrics describe the defined prompt panel, providers, market and dates only. They are "
    "not market share, a universal AI ranking or sales impact."
)
