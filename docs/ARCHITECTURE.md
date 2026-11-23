# ARCHITECTURE

## Layers

```
 Next.js dashboard (web/) ──HTTP /api──▶ FastAPI (src/api/)   user starts runs, reviews, approves
 Streamlit pages (app/, fallback)          │  background jobs for slow/billed work
          │◀───────────────────────────────┘
 src/agent/ (LangGraph, Phase 5)        decides order, pauses for human approval
          │  calls src/services.py, which wires each engine to Postgres
 Engines: plain Python, pydantic in/out
   discovery → diagnostics → opportunities → copilot → experimentation
          │
 src/db.py → Supabase Postgres + pgvector
   Bronze (raw) → Silver (parsed) → Gold (metrics) → action tables
```

Rules: engines never import Streamlit, FastAPI or LangGraph. UI, CLI scripts, agent and tests
all call the same engine functions. Steps pass IDs (`run_id`, `opportunity_id`),
not data. Keys come only from `.env` through `src/config.py`.

## Phase status

Order follows the project charter v2.0. Storage: Supabase only (Databricks deferred).

| Phase | Engine | Status |
|---|---|---|
| 0 | config, db, migrations, smoke test | done |
| 1 | `src/discovery` | **built** (needs API keys for a real run) |
| 2 | `src/diagnostics` | **built to charter**: visibility, accuracy, sources, repeatability, human validation. Parsing/metrics need no keys; sentiment and accuracy extraction need OpenAI |
| 3 | `src/opportunities` | **built**: 6 gap rules, statistical confidence, effort, priority, evidence, template recommendations with approval |
| 4 | `src/copilot` | **built**: approved-doc knowledge base (pgvector), grounded drafts with citation check, human review |
| 5 | `src/agent` | **built**: LangGraph workflow, Postgres checkpoints, human-review interrupt, trace log |
| 6 | `src/experimentation` | **built**: plan/re-test/compare with CI and p-value, repeat-baseline noise design |
| 7 | integration & dashboard | **built**: overview dashboard (Home) + 7 workflow pages, `src/services.py`, `src/reporting.py` |
| 8 | evaluation & delivery | validation framework in place; real-data runs, D1–D7/E1–E2 evidence pending |

## Phase 1: Discovery

```
data/reference/prompt_panel_<v>.csv
        │ panel.load_panel()  (validate columns, unique ids/text)
        ▼
 runner.run_discovery(DiscoveryInput, Settings, RunRepository) → DiscoveryOutput
        │  for each enabled provider: one bronze_runs row
        │  prompts × repeats → thread pool → providers.ask_<provider>()
        │  transient errors (429, 5xx, timeouts) retried 3× with backoff
        ▼
 repository.PostgresRunRepository  → bronze_runs, bronze_responses
   success: raw_response (untouched), answer_text, tokens, cost, latency
   failure: request + error text + http_status (row kept, never dropped)
```

| File | Responsibility |
|---|---|
| `models.py` | `PromptRow`, `ProviderAnswer`, `DiscoveryInput/Output/Plan` |
| `providers.py` | `ask_perplexity`, `ask_openai`, `ask_gemini` (+ `resolve_gemini_source`), response parsers, `estimate_cost`, provider registry |
| `panel.py` | load/validate panel CSV, `sync_brands`, `sync_prompts` |
| `repository.py` | `RunRepository` protocol, Postgres implementation, `list_recent_runs` |
| `runner.py` | `plan_discovery` (dry run, no calls), `run_discovery`, retry logic |

Entry points: `scripts/run_discovery.py` (CLI, `--dry-run` works without keys),
`app/pages/1_Discovery.py` (UI), `scripts/smoke_test_providers.py` (1 call per provider).

Adding a provider: write `ask_<name>(cfg, api_key, question) -> ProviderAnswer`, register it
in `PROVIDERS`, add `<NAME>_API_KEY` to `Settings` and `.env.example`, add it to the YAML.

## Secrets and safety
- API keys are passed into client functions, never stored. `request` columns hold the payload only.
- Runs refuse to start if a needed key is missing; nothing is written.
- Each response is committed as it arrives, so a crash keeps the data collected so far.

## Phase 2: Diagnostics

```
bronze_responses ──▶ parsing.parse_response()      (rules, parser v1, no API)
                      ├─ citations → silver_citations   (url, normalised domain, position)
                      └─ mentions  → silver_brand_mentions (one row per brand per response:
                                     mentioned, count, first position, list rank, snippet)
silver_* + domains ─▶ metrics.compute_visibility / compute_source_share   (metric v1)
                      → gold_visibility, gold_source_share
optional: classifier.label_mention() (OpenAI, analysis model) → sentiment, is_recommended
          → Gold refreshed so positive_rate is filled in
```

| File | Responsibility |
|---|---|
| `models.py` | `ResponseRecord`, `CitationRow`, `MentionRow`, `VisibilityRow`, `SourceShareRow`, inputs/outputs |
| `parsing.py` | domain normalisation and classification, alias matching, list-rank detection, snippets |
| `metrics.py` | metric definitions (see DATA_DICTIONARY) |
| `classifier.py` | structured-output LLM labelling of one mention |
| `reference.py` | load and validate `domains_<v>.csv` |
| `repository.py` | `DiagnosticsRepository` protocol, Postgres implementation, `sync_domains`, UI queries |
| `engine.py` | `diagnose()`, `refresh_gold()`, `classify_mentions()` |

Re-running is safe: Silver is upserted and **keeps existing LLM labels**; Gold is recomputed from Silver.
Entry points: `scripts/run_diagnostics.py`, `app/pages/2_Visibility.py`.

### Phase 2 additions (charter v2.0)
The charter keeps three dimensions separate: **visibility** (present?), **accuracy** (correct?),
**trust/sources** (what evidence?).

```
products_v1.csv ──▶ parse_product_mentions() ─▶ silver_product_mentions
reference_facts_v1.csv ─▶ check_accuracy():
     facts whose subject is mentioned → accuracy.extract_claims() (LLM: what does the answer state?)
                                     → accuracy.compare_value()  (rules v1: match/mismatch/...)
     → silver_accuracy_checks → metrics.compute_accuracy() → gold_accuracy
repeated prompts ─▶ metrics.compute_repeatability() ─▶ gold_repeatability
validation: draw_sample() → labelling CSVs (2 people) → read_sheet() → evaluate()
            → precision / recall / F1, rank accuracy, sentiment macro-F1, Cohen's kappa
```

| File | Responsibility |
|---|---|
| `accuracy.py` | LLM claim extraction (structured output) + rule comparison |
| `validation.py` | stratified sampling, labelling sheets, P/R/F1, macro-F1, kappa, evaluation report |
| `reference.py` | also loads `products_<v>.csv`, `reference_facts_<v>.csv` (validated) |
| `repository.py` | also `sync_reference()`, products/facts/accuracy/repeatability storage |

Entry points: `scripts/run_diagnostics.py --accuracy`, `scripts/validation.py sample|import|evaluate`,
`app/pages/3_Validation.py`.

## Phases 3–7

```
gold_* + silver_* ─▶ opportunities.rules.find_gaps()  (rules v1, no API)
                    → opportunities (severity, confidence, effort, priority, evidence ids)
                    → recommendations (template_v1, status proposed → human approves/rejects)
data/knowledge/*.md ─▶ copilot.ingest_knowledge()  → kb_documents / kb_chunks (pgvector)
opportunity ─▶ copilot.draft_content(): embed query → top-k chunks → LLM draft citing [chunk_id]
            → check_grounding() → content_variants (draft → human approves/rejects)
agent (LangGraph): discover → diagnose → opportunities → draft → ⏸ human_review
                   → plan_experiments → report     (checkpoints in Postgres, agent_runs table)
experimentation: create_experiment() → run_retest() (discovery run_type=retest, same provider,
                 experiment prompts) → diagnose → compare(): delta, 95% CI, p (observational)
```

| Module | Entry points |
|---|---|
| `src/opportunities` | `find_opportunities()`; `scripts/run_opportunities.py`; page 4 |
| `src/copilot` | `ingest_knowledge()`, `draft_content()`; `scripts/ingest_knowledge.py`; page 5 |
| `src/agent` | `start_run()`, `resume_run()`, `get_run()`; `scripts/run_agent.py`; page 6 |
| `src/experimentation` | `create_experiment()`, `run_retest()`, `compare_experiment()`; `scripts/run_experiment.py`; page 7 |
| `src/services.py` | one function per engine, wired to Postgres (used by agent, UI, CLI) |
| `src/reporting.py` | dashboard queries + tested KPI helpers; overview endpoint |
| `src/api/` | `main.py` FastAPI routes (reads + job starts), `jobs.py` in-memory job manager, `queries.py` extra reads |

## Dashboard (Next.js)

`web/` is a client-rendered Next.js 16 app (App Router, Tailwind 4, shadcn/ui, Recharts).
`next.config.ts` proxies `/api/*` to the FastAPI server (`API_URL`, default `http://127.0.0.1:8000`),
so the browser never sees database credentials and there is no CORS. Long work is started with
`POST /api/jobs/...`, which returns a job id; the page polls `GET /api/jobs/{id}` for progress.
Jobs live in API memory only; results are always written to the database by the engines.
`src/lib/api.ts` holds the TypeScript types for every endpoint; `src/hooks/use-api.ts` the fetch and
job-polling hooks. Brand colours are fixed per brand (`src/lib/brands.ts`).
