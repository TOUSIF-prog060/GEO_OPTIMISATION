"""Validation: how well do the automatic parser and labels agree with humans?"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.config import get_settings  # noqa: E402
from src.db import get_conn  # noqa: E402
from src.diagnostics.repository import PostgresDiagnosticsRepository  # noqa: E402
from src.diagnostics.validation import (  # noqa: E402
    evaluate,
    load_labels,
    load_system_mentions,
    read_sheet,
    save_labels,
)

st.set_page_config(page_title="Validation", layout="wide")
st.title("3 · Validation")
st.caption(
    "Human-labelled sample vs the system's output: precision, recall, F1 and "
    "labeller agreement (charter D4/D5 evidence)."
)

with st.expander("How it works", expanded=True):
    st.markdown(
        """
1. **Draw a sample** (command line):
   `python scripts/validation.py sample --latest --n 100 --version s1 --labellers TS AB`
2. **Two people label independently.** Each fills their own CSV in `data/processed/validation/`:
   `mentioned` (yes/no), `rank_in_list` (1, 2, … or blank), `sentiment`
   (positive/neutral/negative/mixed), `is_recommended` (yes/no), `notes`.
3. **Upload** both sheets below (or use `scripts/validation.py import`).
4. **Evaluate.** Items where the labellers disagree are excluded from the reference and counted.
"""
    )

settings = get_settings()
if not settings.supabase_db_url:
    st.warning("SUPABASE_DB_URL is not set in .env. Connect the database to use this page.")
    st.stop()

version = st.text_input("Sample version", value="s1")

st.subheader("Upload a labelled sheet")
c1, c2 = st.columns([1, 3])
labeller = c1.text_input("Labeller initials")
upload = c2.file_uploader("Filled CSV", type="csv")
if st.button("Import labels", disabled=not (upload and labeller)):
    try:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(upload.getvalue())
        labels = read_sheet(Path(tmp.name), labeller.strip().upper())
        if {lab.sample_version for lab in labels} - {version}:
            st.error(f"This sheet is not for sample {version}.")
        else:
            with get_conn() as conn:
                repo = PostgresDiagnosticsRepository(conn)
                brand_ids = {b.name: b.brand_id for b in repo.load_brands()}
                n = save_labels(conn, labels, brand_ids)
            st.success(f"Imported {n} labels from {labeller}.")
    except Exception as exc:
        st.error(f"Import failed: {exc}")

st.subheader("Evaluation")
try:
    with get_conn() as conn:
        labels = load_labels(conn, version)
        system = load_system_mentions(conn, version)
        brand_ids = {b.name: b.brand_id for b in PostgresDiagnosticsRepository(conn).load_brands()}
except Exception as exc:
    st.error(f"Database error: {exc}")
    st.stop()

if not labels:
    st.info(f"No labels for sample {version} yet.")
    st.stop()

rep = evaluate(version, labels, system, brand_ids)
k = st.columns(4)
k[0].metric("Mention precision", rep.mentioned.precision)
k[1].metric("Mention recall", rep.mentioned.recall)
k[2].metric("Mention F1", rep.mentioned.f1)
k[3].metric("Labeller agreement (κ)", rep.kappa_mentioned)
k = st.columns(4)
k[0].metric("Items labelled", rep.n_items)
k[1].metric("Labeller disagreements", rep.n_disagreements)
k[2].metric("Rank accuracy", rep.rank_accuracy, help=f"n = {rep.rank_n}")
k[3].metric("Sentiment macro-F1", rep.sentiment_macro_f1, help=f"n = {rep.sentiment_n}")
st.caption(
    "κ: <0.4 weak, 0.4–0.6 moderate, 0.6–0.8 substantial, >0.8 near-perfect agreement. "
    "Metrics apply only to this sample."
)
if rep.errors:
    st.subheader("Error analysis (system ≠ humans)")
    st.dataframe(pd.DataFrame(rep.errors), width="stretch", hide_index=True)
