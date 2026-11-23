# ARCHITECTURE

## Layers

```
 Streamlit pages (app/)                 user starts runs, reviews, approves
          │
 src/agent/ (LangGraph, Phase 6)        decides order, pauses for human approval
          │  calls only the engine functions below
 Engines: plain Python, pydantic in/out
   discovery → diagnostics → opportunities → copilot → experimentation
          │
 src/db.py → Supabase Postgres + pgvector
   Bronze (raw) → Silver (parsed) → Gold (metrics) → action tables
```

Rules: engines never import Streamlit or LangGraph. UI, CLI scripts, agent and tests
all call the same engine functions. Steps pass IDs (`run_id`, `opportunity_id`),
not data. Keys come only from `.env` through `src/config.py`.

## Phase status

| Phase | Engine | Status |
|---|---|---|
| 0 | config, db, migrations, smoke test | done |
| 1 | `src/discovery` | **built** (needs API keys for a real run) |
| 2 | `src/diagnostics` | not started |
| 3 | `src/opportunities` | not started |
| 4 | `src/copilot` | not started |
| 5 | `src/experimentation` | not started |
| 6 | `src/agent` | not started |
| 7 | dashboard pages | Discovery page only |

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
| `providers.py` | `ask_perplexity`, `ask_openai`, response parsers, `estimate_cost`, provider registry |
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
