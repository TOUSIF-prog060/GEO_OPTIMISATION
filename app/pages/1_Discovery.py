"""Discovery: preview the prompt panel, plan a run, start it, and see recent runs."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_settings  # noqa: E402
from src.db import get_conn  # noqa: E402
from src.discovery import DiscoveryInput, plan_discovery, run_discovery  # noqa: E402
from src.discovery.panel import (  # noqa: E402
    REFERENCE_DIR,
    load_panel,
    panel_path,
    sync_brands,
    sync_prompts,
)
from src.discovery.repository import PostgresRunRepository, list_recent_runs  # noqa: E402

st.set_page_config(page_title="Discovery", layout="wide")
st.title("1 · Discovery")
st.caption("Ask AI answer engines the prompt panel and store their raw answers (Bronze).")

settings = get_settings()
versions = sorted(
    p.stem.removeprefix("prompt_panel_") for p in REFERENCE_DIR.glob("prompt_panel_*.csv")
)
if not versions:
    st.error(f"No prompt panels in {REFERENCE_DIR}. Add prompt_panel_<version>.csv.")
    st.stop()

# ---------------------------------------------------------------- panel
version = st.selectbox("Prompt panel", versions, index=len(versions) - 1)
try:
    rows = load_panel(panel_path(version))
except (ValueError, FileNotFoundError) as exc:
    st.error(str(exc))
    st.stop()

df = pd.DataFrame([r.model_dump() for r in rows])
c1, c2, c3 = st.columns(3)
c1.metric("Prompts", len(df))
c2.metric("Categories", df["category"].nunique())
c3.metric("Intents", df["intent"].nunique())
with st.expander("Preview panel"):
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------- run settings
st.subheader("Run")
enabled = [p.name for p in settings.project.providers if p.enabled]
cols = st.columns(4)
providers = cols[0].multiselect("Providers", enabled, default=enabled)
repeats = cols[1].number_input("Repeats per prompt", 1, 10, 1)
limit = cols[2].number_input("Limit prompts (0 = all)", 0, len(df), 0)
workers = cols[3].number_input("Parallel calls", 1, 16, 4)

if not providers:
    st.warning("Pick at least one provider.")
    st.stop()

inp = DiscoveryInput(
    panel_version=version,
    providers=providers,
    repeats=int(repeats),
    limit=int(limit) or None,
    max_workers=int(workers),
)
plan = plan_discovery(inp, settings)
st.info(
    f"**{plan.n_calls} API calls** = {plan.n_prompts} prompts × "
    f"{len(plan.providers)} provider(s) × {plan.repeats} repeat(s). These are real, billed calls."
)

blockers = []
if plan.missing_keys:
    missing = ", ".join(k.upper() + "_API_KEY" for k in plan.missing_keys)
    blockers.append(f"Missing API key(s) in .env: {missing}")
if not settings.supabase_db_url:
    blockers.append("SUPABASE_DB_URL is not set in .env")
for b in blockers:
    st.warning(b)

confirm = st.checkbox("I understand this spends API credit")
if st.button("Start run", type="primary", disabled=bool(blockers) or not confirm):
    bar = st.progress(0.0, text="Starting…")

    def progress(provider: str, done: int, total: int) -> None:
        bar.progress(done / total, text=f"{provider}: {done}/{total}")

    try:
        with get_conn() as conn:
            sync_brands(conn, settings.project)
            sync_prompts(conn, rows, version)
            out = run_discovery(inp, settings, PostgresRunRepository(conn), on_progress=progress)
        st.success("Run finished")
        st.dataframe(pd.DataFrame([r.model_dump() for r in out.runs]), hide_index=True)
    except Exception as exc:
        st.error(f"Run failed: {exc}")

# ---------------------------------------------------------------- history
st.subheader("Recent runs")
if not settings.supabase_db_url:
    st.caption("Connect the database to see run history.")
else:
    try:
        with get_conn() as conn:
            runs = list_recent_runs(conn)
        if runs:
            st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)
        else:
            st.caption("No runs yet.")
    except Exception as exc:
        st.error(f"Could not load runs: {exc}")
