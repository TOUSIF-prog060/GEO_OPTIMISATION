# Decision Log

One entry per decision: date, decision, alternatives considered, reason, owner.

## 2026-11-22 — Discovery providers
- **Decision:** Perplexity Sonar API (provider 1) and OpenAI Responses API with the `web_search` tool (provider 2).
- **Alternatives:** Google Gemini with grounding; scraping consumer chat UIs (rejected because of terms of service and reproducibility).
- **Reason:** Both return web-grounded answers with citation URLs, close to what users see. Two engines allow a provider comparison. OpenAI is also used for generation and embeddings.
- **Model names:** kept in `configs/beauty_india.yaml`, not in code. Verified on: _TODO_
- **Owner:** _TODO_

## 2026-11-22 — Database
- **Decision:** One Supabase Postgres database with pgvector. Bronze/Silver/Gold layers are table-name prefixes.
- **Alternatives:** Databricks (deferred to Phase 9, only if faculty requires it); SQLite plus a separate vector store.
- **Reason:** App state, analytics tables and vectors live in one place at pilot scale, on a free tier.
- **Owner:** _TODO_

## 2026-11-22 — Cost per call
- **Perplexity:** _TODO: fill in from the smoke test token counts and the pricing page_
- **OpenAI (web search):** _TODO_
- **Pricing checked on:** _TODO_

## 2026-11-23 — Discovery engine design (Phase 1)
- **Decision:** One `bronze_runs` row per provider per run; prompts × repeats called in a thread pool (default 4); DB writes on the main thread, committed per response. Transient errors (408/409/429/5xx, timeouts) retried 3× with 2s/4s backoff; other failures stored as error rows.
- **Alternatives:** asyncio clients (more complex for little gain at pilot scale); one run row covering all providers (makes provider comparison and partial re-runs harder).
- **Reason:** Simple, resumable, every call accounted for, matches the "never drop data" rule.
- **Owner:** _TODO_

## 2026-11-23 — Prompt panel v0
- **Decision:** `data/reference/prompt_panel_v0.csv`, 30 prompts. A draft to build and test the pipeline with. Covers retailer choice (where to buy, authenticity, offers, direct comparisons) plus product categories (sunscreen, moisturiser, serum, makeup, haircare, fragrance, gifting).
- **Status:** Draft. The team must review and expand it into v1 (target 100–200 prompts) before the real baseline run. Do not edit v0 after a run has used it; create a new version instead.
- **Owner:** _TODO_

## 2026-11-23 — Diagnostics design (Phase 2)
- **Decision:** Mentions, ranks and citations are parsed with deterministic rules (parser v1); all Gold metrics are computed in plain Python from Silver. The LLM is used only for the optional sentiment / is_recommended labels, recorded with `classified_by`.
- **Alternatives:** LLM extraction of everything (not reproducible, costs per re-run, harder to defend); fuzzy matching with rapidfuzz (false positives on short names like "Tira").
- **Reason:** Reproducible numbers, zero cost to re-run, every metric traceable to a response_id.
- **Owner:** _TODO_

## 2026-11-23 — Domain reference v1
- **Decision:** `data/reference/domains_v1.csv`, 18 well-known domains (own site, 2 competitors, marketplaces, beauty editorial, forums, YouTube). Draft.
- **Status:** Extend after the first real run using the "unclassified domains" list on the Visibility page; save as v2.
- **Owner:** _TODO_

## 2026-11-23 — Migration runner fix
- **Decision:** `run_migrations()` records filenames with `ON CONFLICT DO NOTHING`, because migrations 002+ record themselves so they can also be pasted into the Supabase SQL editor. Without this the runner would fail on 002.

## 2026-11-23 — Supabase only (charter v2.0 reconciliation)
- **Decision:** Keep Supabase Postgres as the single store for app and analytics data for now. The charter's Databricks/Delta layer is deferred; revisit only if faculty requires it.
- **Also:** Phase order follows charter v2.0: 3 Opportunities, 4 Copilot, 5 Agent, 6 Experimentation, 7 Integration, 8 Evaluation & delivery.
- **Owner:** _TODO_

## 2026-11-23 — Phase 2 completed to charter v2.0
- **Accuracy = LLM extraction + rule comparison.** The LLM only reports what the answer *states* (or null); a versioned rule set (checker v1) decides match / mismatch / not_mentioned / unverifiable. Keeps the judgement reproducible and lets extraction be evaluated separately. Only facts whose subject the answer mentions are checked.
- **Reference catalogue ships empty.** `products_v1.csv` and `reference_facts_v1.csv` have headers only. Every row needs a real source_url and last_verified_at; no values are guessed.
- **Confidence is NULL for rule-based extraction.** A made-up score would be misleading; probabilistic extractors (the D4 ML candidate) will fill it.
- **Repeatability** = agreement across repeats + mean within-prompt SD of the 0/1 mention indicator.
- **Validation reference = labeller consensus.** Items where labellers disagree are counted and excluded; Cohen's kappa reports agreement. Metrics implemented in plain Python (no scikit-learn dependency).
- **Deferred to D4:** ML/NLP candidate (spaCy / scikit-learn) vs the rule baseline, and intent classification, because they need the human labels first.
- **Owner:** _TODO_

## 2026-11-23 — Agent dependencies
- **Decision:** Add `langgraph` (1.2.x) and `langgraph-checkpoint-postgres` (3.2.x), approved by the user. Agent checkpoints are stored in Supabase so a run paused for human approval (or interrupted) can resume.
- **Alternatives:** in-memory checkpoints only; a plain-Python state machine (deviates from charter stack).

## 2026-11-23 — Phase 3 Opportunities (rules v1)
- **Decision:** six deterministic gap rules with thresholds: mention gap ≥ 0.15, rank gap ≥ 1 position, citation gap ≥ 0.10, positive-rate gap ≥ 0.20, repeat agreement < 0.70, categories need ≥ 3 answers. Effort by gap type (accuracy low; visibility/ranking/sentiment medium; citation/stability high).
- **Confidence** uses a one-sided two-proportion z-test where a gap is between two rates; elsewhere the documented heuristic n/(n+10). Opportunities are observations on the prompt sample, not proof of a market-wide problem.
- **Recommendations** are deterministic templates (template_v1) linked to the same evidence; the copilot writes content only after a human reviews.

## 2026-11-23 — Phase 4 Copilot (RAG)
- **Decision:** knowledge base = approved Markdown docs in `data/knowledge/` (title, source_url, verified_at required); ~900-char paragraph chunks; OpenAI `text-embedding-3-small` (1536-d) in pgvector with HNSW cosine index; top-6 retrieval.
- **Grounding:** the LLM must cite chunk ids, list unsupported claims and flag missing info; a rule check marks drafts with citations outside the retrieved set. Drafts are never auto-approved or published.

## 2026-11-23 — Phase 5 Agent
- **Decision:** LangGraph StateGraph: discover → diagnose → opportunities → draft → human_review (interrupt) → plan_experiments → report. Nodes call engines via an `AgentTools` interface (fakes in tests). Retries (2 attempts) on discovery/diagnosis/opportunity nodes; draft failures are logged, not fatal. Checkpoints in Postgres; run status in `agent_runs`.

## 2026-11-23 — Phase 6 Experimentation
- **Decision:** compare mention rate on the experiment's prompt subset, baseline vs re-test, same provider; report delta, 95% Wald CI and two-sided z-test p. A `repeat_baseline` design (no change) measures run-to-run noise. Every interpretation states it is observational. No causal claims.

## 2026-11-23 — Phase 7 Dashboard
- **Decision:** `app/Home.py` is the overview dashboard (status, workflow counts, KPI deltas per provider, trends, category heatmap, top opportunities, operations). Queries in `src/reporting.py`; engine wiring for UI/agent/CLI in `src/services.py`.

## 2026-11-24 — Gemini added as the third measured engine
- **Decision:** Google Gemini `gemini-2.5-flash` via the REST `generateContent` endpoint with the `google_search` grounding tool (httpx, no new dependency). Key: `GEMINI_API_KEY`. Model name checked against `models.list` on 2026-11-24.
- **Citations:** Gemini returns each grounding source as a short-lived `vertexaisearch.cloud.google.com` redirect plus the source domain as `title`. The citation URL is `https://<title>` when the title is a bare domain (else the URI). Derived from the stored raw payload only, so diagnostics can re-derive it at any time (redirects expire). Page-level URLs are not available; domain-level source share is.
- **Prices:** not yet filled in; cost shows as blank until the pricing page is checked.

## 2026-11-24 — Next.js dashboard with a FastAPI backend
- **Decision:** replace Streamlit as the main UI with a Next.js dashboard (`web/`), backed by a FastAPI API (`src/api/`). Streamlit stays as a fallback. New dependencies approved by the user: `fastapi`, `uvicorn` (Python); `next`, `react`, `tailwindcss`, shadcn/ui (`radix-ui`, `cn`, `class-variance-authority`), `recharts`, `lucide-react`, `next-themes`, `sonner` (npm).
- **Why an API in between:** the dashboard reuses the tested Python queries and engines instead of re-writing SQL in TypeScript, and the database URL stays server-side. Next.js proxies `/api/*` to FastAPI.
- **Jobs:** discovery, measuring, drafting, the agent and re-tests run in a 2-worker thread pool and are polled for progress. Jobs are in memory; data is in the database.
- **Charts:** rates are plotted on a fixed 0–100% axis and ranks from 0 so bar lengths are honest. Brand colours are fixed: Sephora India plum, Nykaa rose, Tira teal.

## 2026-11-24 — Ask your own question
- **Decision:** the dashboard lets a user type up to 10 questions and pick engines. They go through the normal discovery engine (raw answers stored, retries, lineage) as an `adhoc` run on the `custom` prompt set, then are measured automatically (rules only, free).
- **Why not a plain chat box:** every answer must be stored and traceable; the stable hash id lets a repeated question be compared over time; `adhoc` keeps one-off questions out of the panel-based headline metrics, which need a fixed question set to be comparable.
- **Database connection:** switched `SUPABASE_DB_URL` to the Supabase session pooler (IPv4). The direct host is IPv6-only and failed when the local network lost IPv6; hosting platforms also need the pooler.
