# CLAUDE.md — Beyond the Search Bar

## What this project is
An AI Discovery Intelligence Platform (GEO). It measures how AI answer engines
represent a brand, diagnoses gaps, recommends fixes, drafts content and
re-tests. Pilot: Sephora India vs Nykaa and Tira, beauty/skincare, India.
XIME analytics capstone, team of 3.

## Stack
Python 3.11, Streamlit (UI), Supabase Postgres + pgvector (app data,
analytics tables, vectors), Perplexity Sonar / OpenAI web-search API
(discovery), LangGraph (agent), Plotly, pytest, pydantic, MLflow (optional).
Databricks only if faculty requires it (Phase 9 migration).

## Rules
- Build one phase at a time. Do not start a later phase unasked.
- Plan first, then code. Keep functions small and typed.
- Every engine is a plain Python module in src/<engine>/ with a clear
  input/output pydantic model. UI and agent only call these functions.
- Never hardcode keys. Read them from .env via src/config.py.
- Never invent data, metrics or citations. Store raw API responses as-is.
- Every derived record keeps the IDs of its source (run_id, response_id).
- Prompt sets, reference data and content variants are versioned.
- Write pytest tests for every engine function; mock API calls in tests.
- Log errors; never swallow exceptions silently.
- Update docs/DATA_DICTIONARY.md when you change a schema.
- Ask before adding a new dependency or a new external service.

## Commands
- Run app: streamlit run app/Home.py
- Tests: pytest -q
- Lint: ruff check . && ruff format .
