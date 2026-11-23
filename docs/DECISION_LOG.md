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
