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
