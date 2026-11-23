"""Experimentation Lab: plan re-tests, run them, compare with the baseline."""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src import services  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.copilot.repository import list_variants  # noqa: E402
from src.db import get_conn  # noqa: E402
from src.diagnostics.repository import list_runs  # noqa: E402
from src.experimentation.repository import list_experiments, load_results  # noqa: E402

st.set_page_config(page_title="Experiments", layout="wide")
st.title("7 · Experimentation Lab")
st.caption(
    "Re-ask the affected prompts after a change and compare with the baseline. Results are "
    "**observational**: AI answers vary between runs and other sites change too. Run a "
    "*repeat baseline* (no change) to see normal run-to-run noise."
)

settings = get_settings()
if not settings.supabase_db_url:
    st.warning("SUPABASE_DB_URL is not set in .env. Connect the database to use this page.")
    st.stop()

try:
    with get_conn() as conn:
        runs = list_runs(conn)
        approved = [v for v in list_variants(conn) if v["status"] == "approved"]
        exps = list_experiments(conn)
except Exception as exc:
    st.error(f"Database error: {exc}")
    st.stop()

st.subheader("Plan an experiment")
if not runs:
    st.info("No discovery runs yet.")
else:
    run_labels = {r["run_id"]: f"{r['started_at']:%Y-%m-%d %H:%M} · {r['provider']}" for r in runs}
    baseline = st.selectbox("Baseline run", list(run_labels), format_func=run_labels.get)
    design = st.radio("Design", ["content_variant", "repeat_baseline"], horizontal=True)
    variant = None
    if design == "content_variant":
        if not approved:
            st.caption("No approved drafts yet (Copilot page).")
        else:
            vl = {v["variant_id"]: f"v{v['version']} · {v['title']}" for v in approved}
            variant = st.selectbox("Approved content variant", list(vl), format_func=vl.get)
    if st.button("Plan", disabled=design == "content_variant" and not variant):
        opp = next((v["opportunity_id"] for v in approved if v["variant_id"] == variant), None)
        try:
            eid = services.plan_experiment(variant, opp, baseline, "ui", design)
            st.success(f"Experiment {eid} planned. Publish the content, then run the re-test.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

st.subheader("Experiments")
if not exps:
    st.caption("None yet.")
    st.stop()
st.dataframe(pd.DataFrame(exps), width="stretch", hide_index=True)
labels = {
    e["experiment_id"]: f"{e['status']} · {e['design']} · {e['variant'] or 'no variant'}"
    for e in exps
}
eid = st.selectbox("Experiment", list(labels), format_func=labels.get)
exp = next(e for e in exps if e["experiment_id"] == eid)
st.markdown(f"**Hypothesis:** {exp['hypothesis']}")

repeats = st.number_input("Repeats per prompt", 1, 10, 3)
if st.button("Run re-test (billed)", disabled=exp["status"] == "done" or not settings.openai_api_key
             and not settings.perplexity_api_key):  # fmt: skip
    with st.spinner("Re-testing…"):
        try:
            services.retest(eid, int(repeats))
            st.rerun()
        except Exception as exc:
            st.error(f"Re-test failed: {exc}")

with get_conn() as conn:
    res = pd.DataFrame(load_results(conn, eid))
if res.empty:
    st.caption("No results yet.")
    st.stop()
fig = go.Figure()
for _, r in res.iterrows():
    fig.add_trace(go.Bar(name=f"{r['brand']} baseline", x=[r["brand"]], y=[r["baseline_value"]],
                         marker_color="#b9b4c7", showlegend=False))  # fmt: skip
    fig.add_trace(go.Bar(
        name=f"{r['brand']} re-test", x=[r["brand"]], y=[r["retest_value"]], marker_color="#574276",
        error_y={"type": "data", "symmetric": False,
                 "array": [max(0, r["ci_high"] - r["delta"])] if pd.notna(r["ci_high"]) else [0],
                 "arrayminus": [max(0, r["delta"] - r["ci_low"])]
                 if pd.notna(r["ci_low"]) else [0]},
        showlegend=False,
    ))  # fmt: skip
fig.update_layout(barmode="group",
                  title="Mention rate: baseline (grey) vs re-test (purple, ±95% CI of change)",
                  yaxis_tickformat=".0%")  # fmt: skip
st.plotly_chart(fig, width="stretch")
st.dataframe(res, width="stretch", hide_index=True)
