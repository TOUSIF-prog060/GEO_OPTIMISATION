"""Beyond the Search Bar — home page. Run: streamlit run app/Home.py"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings  # noqa: E402
from src.db import check_connection  # noqa: E402

st.set_page_config(page_title="Beyond the Search Bar", layout="wide")
st.title("Beyond the Search Bar")
st.caption("AI Discovery Intelligence Platform (GEO) — pilot: beauty & skincare, India")

settings = get_settings()
project = settings.project

st.subheader("System status")
if not settings.supabase_db_url:
    st.error("DB not configured — set SUPABASE_DB_URL in .env")
else:
    ok, message = check_connection(settings.supabase_db_url)
    if ok:
        st.success("DB connected")
        st.caption(message)
    else:
        st.error("DB connection failed")
        st.code(message)

cols = st.columns(len(project.providers))
for col, p in zip(cols, project.providers, strict=True):
    has_key = bool(getattr(settings, f"{p.name}_api_key", None))
    col.metric(p.name, p.model, "key set" if has_key else "no key", delta_color="off")

st.subheader("Pilot")
st.write(f"**Target:** {project.target.name}")
st.write(f"**Competitors:** {', '.join(b.name for b in project.competitors)}")
st.write(f"**Market / language:** {project.market} / {project.language}")
