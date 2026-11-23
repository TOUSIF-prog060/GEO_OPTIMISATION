"""Agent: run the full loop with LangGraph and approve drafts when it pauses."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.agent import get_run, postgres_checkpointer, resume_run, start_run  # noqa: E402
from src.agent.tools import PostgresAgentTools, list_agent_runs  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.db import get_conn  # noqa: E402
from src.diagnostics.repository import list_runs  # noqa: E402

st.set_page_config(page_title="Agent", layout="wide")
st.title("6 · GEO Agent")
st.caption(
    "discover → diagnose → opportunities → draft → **⏸ human review** → plan experiments → "
    "report. The agent only calls the engines; nothing is approved without you."
)

settings = get_settings()
if not settings.supabase_db_url:
    st.warning("SUPABASE_DB_URL is not set in .env. Connect the database to use this page.")
    st.stop()
tools = PostgresAgentTools()

st.subheader("Start a run")
mode = st.radio("Discovery", ["Reuse existing runs (no discovery cost)", "Run new discovery"],
                horizontal=True)  # fmt: skip
params: dict = {}
if mode.startswith("Reuse"):
    try:
        with get_conn() as conn:
            runs = list_runs(conn)
    except Exception as exc:
        st.error(f"Database error: {exc}")
        st.stop()
    labels = {r["run_id"]: f"{r['started_at']:%Y-%m-%d %H:%M} · {r['provider']}" for r in runs}
    params["run_ids"] = st.multiselect("Runs", list(labels), format_func=labels.get,
                                       default=list(labels)[:2])  # fmt: skip
else:
    c = st.columns(3)
    params["panel_version"] = c[0].text_input("Panel", "v0")
    params["limit"] = int(c[1].number_input("Limit prompts (0 = all)", 0, 500, 5)) or None
    params["repeats"] = int(c[2].number_input("Repeats", 1, 5, 1))
c = st.columns(3)
params["max_drafts"] = int(c[0].number_input("Max drafts", 1, 10, 3))
params["label_sentiment"] = c[1].checkbox("LLM sentiment labels")
params["check_accuracy"] = c[2].checkbox("LLM accuracy checks")

needs_key = not settings.openai_api_key
if needs_key:
    st.warning("OPENAI_API_KEY is not set: drafting (and discovery) will fail and be logged.")
if st.button("Start agent", type="primary",
             disabled=mode.startswith("Reuse") and not params.get("run_ids")):  # fmt: skip
    with st.spinner("Agent running…"):
        try:
            with postgres_checkpointer(settings.supabase_db_url) as cp:
                tid, status, pending, values = start_run(tools, cp, params)
            st.session_state["thread"] = tid
            st.success(f"Thread {tid}: {status}")
        except Exception as exc:
            st.error(f"Agent failed: {exc}")

st.subheader("Runs")
try:
    history = list_agent_runs()
except Exception as exc:
    st.error(f"Could not load agent runs (run migration 007?): {exc}")
    st.stop()
if not history:
    st.caption("No agent runs yet.")
    st.stop()
st.dataframe(pd.DataFrame(history), width="stretch", hide_index=True)

threads = [h["thread_id"] for h in history]
default = (
    threads.index(st.session_state["thread"]) if st.session_state.get("thread") in threads else 0
)
tid = st.selectbox("Inspect thread", threads, index=default)
with postgres_checkpointer(settings.supabase_db_url) as cp:
    status, pending, values = get_run(tools, cp, tid)
st.markdown(f"**Status:** {status}")
if values.get("errors"):
    for e in values["errors"]:
        st.warning(e)

if pending:
    st.subheader("⏸ Waiting for your review")
    st.caption("Read the drafts on the Copilot page, then decide here.")
    drafts = pending[0]["drafts"]
    reviewer = st.text_input("Your initials", max_chars=8)
    decisions = {}
    for d in drafts:
        decisions[d["variant_id"]] = st.radio(
            f"{d['title']} (grounded: {d['grounded']})", ["skip", "approve", "reject"],
            horizontal=True, key=f"d-{d['variant_id']}",
        )  # fmt: skip
    if st.button("Submit review and resume", disabled=not reviewer):
        decision = {
            "approved": [v for v, s in decisions.items() if s == "approve"],
            "rejected": [v for v, s in decisions.items() if s == "reject"],
            "reviewer": reviewer,
        }
        with postgres_checkpointer(settings.supabase_db_url) as cp:
            status, pending, values = resume_run(tools, cp, tid, decision)
        st.success(f"Resumed: {status}")
        st.rerun()

if values.get("report"):
    st.subheader("Report")
    st.json(values["report"])
with st.expander("Trace log"):
    st.dataframe(pd.DataFrame(values.get("log", [])), width="stretch", hide_index=True)
