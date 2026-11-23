<div align="center">

# 🔍 Beyond the Search Bar

### AI Discovery Intelligence Platform (GEO)

**How do AI answer engines talk about your brand, and what can you do about it?**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Dashboard-Next.js-000000?logo=nextdotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![Supabase](https://img.shields.io/badge/DB-Supabase%20Postgres-3ECF8E?logo=supabase&logoColor=white)
![pgvector](https://img.shields.io/badge/Vectors-pgvector-336791?logo=postgresql&logoColor=white)
![LangGraph](https://img.shields.io/badge/Agent-LangGraph-1C3C3C)
![Status](https://img.shields.io/badge/status-pilot%20in%20progress-orange)

*XIME Analytics Capstone · Team of 3*

</div>

---

## ✨ What it does

People increasingly ask **ChatGPT, Perplexity, Gemini and other AI engines** what to buy instead of typing into a search bar. This means brands need a new kind of optimisation: **Generative Engine Optimisation (GEO)**.

*Beyond the Search Bar* runs that loop end to end:

```
   ┌──────────┐    ┌──────────┐    ┌───────────┐    ┌─────────┐    ┌──────────┐
   │ MEASURE  │ ─▶ │ DIAGNOSE │ ─▶ │ RECOMMEND │ ─▶ │  DRAFT  │ ─▶ │ RE-TEST  │
   └──────────┘    └──────────┘    └───────────┘    └─────────┘    └──────────┘
   Ask AI engines   Find gaps vs    Prioritised       Generate       Measure the
   a prompt panel   competitors     fixes             content        uplift
        ▲                                                                │
        └────────────────────────────────────────────────────────────────┘
```

| Step | Question it answers |
|---|---|
| 📊 **Measure** | Is the brand mentioned? At what rank? With what sentiment? Which sources are cited? |
| 🩺 **Diagnose** | Where do competitors appear and we don't? Which source types does the AI trust? |
| 💡 **Recommend** | What should change, and in what priority order? |
| ✍️ **Draft** | Versioned content variants aimed at each gap |
| 🔁 **Re-test** | Did visibility actually move? (baseline vs re-test, with stats) |

## 🎯 Pilot

| | |
|---|---|
| **Target brand** | Sephora India |
| **Competitors** | Nykaa, Tira |
| **Category** | Beauty & skincare |
| **Market** | India (English) |
| **AI engines** | Perplexity Sonar · OpenAI (web search) · Google Gemini 2.5 Flash (Search grounding) |
| **First result** | On Gemini, Sephora India is named in 41% of answers; Nykaa leads at 53% (17 answers, 23 Nov 2026, panel v0) |

## 🏗️ Architecture

```
web/  (Next.js dashboard) ──▶ src/api/  (FastAPI)
                                   │
app/  (Streamlit, fallback)        │        src/agent/  (LangGraph)
          │                        │               │
          └──────────┬─────────────┴───────────────┘
                     ▼   plain Python engines with pydantic I/O
   ┌──────────────┬──────────────┬───────────────┬────────────────┬──────────────┐
   │ discovery    │ diagnostics  │ opportunities │ copilot        │ experiment-  │
   │              │              │               │                │ ation        │
   └──────────────┴──────────────┴───────────────┴────────────────┴──────────────┘
                     ▼
        Supabase Postgres + pgvector
        Bronze (raw) ─▶ Silver (parsed) ─▶ Gold (metrics)
```

**Data layers**

- 🥉 **Bronze**: `bronze_runs`, `bronze_responses`. Raw API payloads stored exactly as received and never edited.
- 🥈 **Silver**: `silver_citations`, `silver_brand_mentions`, `silver_response_chunks` (embeddings)
- 🥇 **Gold**: `gold_visibility`, `gold_source_share`. The metrics behind the dashboard.
- 🧪 **Action**: `opportunities`, `recommendations`, `content_variants`, `experiments`, `experiment_results`

Every derived row keeps its `run_id` / `response_id`, so any number on the dashboard can be traced back to the original AI answer. Full schema: [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md).

## 🚀 Quick start

```bash
# 1. Clone
git clone https://github.com/TOUSIF-prog060/GEO_OPTIMISATION.git
cd GEO_OPTIMISATION

# 2. Environment
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"

# 3. Secrets
copy .env.example .env          # macOS/Linux: cp .env.example .env
#   then fill in SUPABASE_DB_URL, PERPLEXITY_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY

# 4. Database
python -m src.db                # applies db/migrations/*.sql
#   (or paste db/migrations/002_core_schema.sql into the Supabase SQL editor)

# 5. Dashboard (needs Node.js 20+)
cd web && npm install && cd ..
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#   API on http://localhost:8000 (docs at /docs), dashboard on http://localhost:3000
#   or by hand: uvicorn src.api.main:app --port 8000   and   cd web && npm run dev
```

> 💸 `python scripts/smoke_test_providers.py` sends **one real, billed** question to each AI engine. Use it to confirm your keys work.

## 🧰 Commands

| Task | Command |
|---|---|
| Dashboard (API + Next.js) | `powershell -File scripts\dev.ps1` |
| API only | `uvicorn src.api.main:app --port 8000` |
| Dashboard only | `cd web && npm run dev` |
| Old Streamlit UI (fallback) | `streamlit run app/Home.py` |
| Dashboard checks | `cd web && npx tsc --noEmit && npm run lint` |
| Tests | `pytest -q` |
| Lint & format | `ruff check . && ruff format .` |
| Apply migrations | `python -m src.db` |
| Provider smoke test | `python scripts/smoke_test_providers.py` |
| Discovery: plan only (no keys needed) | `python scripts/run_discovery.py --panel v0 --dry-run` |
| Discovery: small test run | `python scripts/run_discovery.py --panel v0 --limit 5` |
| Discovery: full baseline | `python scripts/run_discovery.py --panel v0 --repeats 3` |
| Diagnostics: metrics for newest run (free) | `python scripts/run_diagnostics.py --latest` |
| Diagnostics: + LLM sentiment labels | `python scripts/run_diagnostics.py --latest --classify` |
| Diagnostics: + LLM fact-accuracy checks | `python scripts/run_diagnostics.py --latest --accuracy` |
| Validation: draw sample + labelling sheets | `python scripts/validation.py sample --latest --n 100 --version s1 --labellers TS AB` |
| Validation: import / evaluate | `python scripts/validation.py import ...` · `python scripts/validation.py evaluate --version s1` |
| Opportunities (free) | `python scripts/run_opportunities.py --latest` |
| Knowledge base: embed approved docs | `python scripts/ingest_knowledge.py` |
| Agent: full loop (pauses for review) | `python scripts/run_agent.py start --panel v0 --limit 5` |
| Agent: approve and resume | `python scripts/run_agent.py resume --thread <id> --approve <variant_id> --reviewer TS` |
| Experiments | `python scripts/run_experiment.py plan ...` · `retest --experiment <id>` · `list` |
| Sandbox evaluation (free) | `python -m evals.run` · add `--live` for a real model stability test · results in [`docs/EVALUATION.md`](docs/EVALUATION.md) |
| Evaluation PDF for manual review | `python -m evals.report_pdf` → `reports/evals/evaluation_report_<time>.pdf` |

## 🔎 Discovery engine (Phase 1)

Asks each AI engine every prompt in the panel and stores the raw answers in Bronze.

```
prompt_panel_v0.csv ─▶ run_discovery() ─▶ Perplexity Sonar ┐
                                     └──▶ OpenAI web search ┴─▶ bronze_runs / bronze_responses
```

- **Prompt panel:** [`data/reference/prompt_panel_v0.csv`](data/reference/prompt_panel_v0.csv) has 30 draft prompts (retailer choice, authenticity, Nykaa vs Sephora vs Tira, sunscreen, serums, makeup, haircare, fragrance). New panels go in as `prompt_panel_<version>.csv`. Don't edit a panel after a run has used it.
- **Keys:** read only from `.env` and passed into the call functions. They're never stored. A run refuses to start if a key is missing, and the dry run shows which one.
- **Reliability:** 4 parallel calls; timeouts, 429s and 5xx errors retried 3× with backoff; failed calls saved as error rows, never dropped; each answer committed as it arrives.
- **Cost:** estimated per call from the prices in `configs/beauty_india.yaml` (fill these in).
- **UI:** dashboard → **Ask the engines**: panel preview, call count, start a run, live progress, run history.

## 📊 Diagnostics engine (Phase 2)

Turns raw answers into facts (Silver) and visibility metrics (Gold). Parsing and metrics are rule-based, so they're **free, reproducible and need no API key**.

| Metric | Meaning |
|---|---|
| **Mention rate** | % of answers that name the brand |
| **Share of voice** | brand's share of all brand mentions (Sephora vs Nykaa vs Tira) |
| **Avg rank** | position when the answer is a ranked list (1 = top) |
| **Citation share** | % of cited sources that are the brand's own site |
| **Positive rate** | % of mentions with positive tone (optional LLM labelling) |
| **Source share** | which domains and source types (retailer, editorial, forum, video) AI engines cite |
| **Repeatability** | how consistently a brand appears when the same prompt is asked again |
| **Accuracy** | whether facts stated about brands/products match verified reference facts |

- Each metric is computed per run, overall and per category, and every number traces back to a `response_id`.
- Brand matching is whole-word on the aliases in `configs/beauty_india.yaml` (so "Tira" ≠ "tiramisu").
- Websites are classified with [`data/reference/domains_v1.csv`](data/reference/domains_v1.csv). Unknown ones are listed on the page so you can add them.
- **Three separate dimensions** (charter): **visibility** (is the brand present?), **accuracy** (are stated facts correct?), **sources** (what evidence is cited?).
- **Accuracy checks:** the LLM only extracts what an answer *states*; versioned rules decide match / mismatch / not mentioned / unverifiable against [`reference_facts_v1.csv`](data/reference/reference_facts_v1.csv). Product tracking uses [`products_v1.csv`](data/reference/products_v1.csv). Both ship empty: fill them with verified values and source URLs ([guide](data/reference/README.md)).
- **Human validation:** a stratified sample is labelled by two people, then precision, recall, F1 and Cohen's kappa measure how well the parser agrees with humans (D4/D5 evidence).
- **UI:** **Visibility** page (run diagnostics, sentiment, accuracy, repeatability, charts) and **Validation** page (upload labels, see evaluation).

## 🎯 Opportunities, Copilot, Agent and Experiments (Phases 3–6)

| Phase | What it does | Human in the loop |
|---|---|---|
| **3 Opportunities** | 6 rule-based gap types (missing from a category, ranked lower, cited less, more negative tone, wrong facts, unstable presence). Each has severity, **statistical confidence**, effort, priority and the evidence answers. | Approve / reject each recommendation |
| **4 Copilot** | Writes FAQs, buying guides and content briefs **only from approved brand documents** in `data/knowledge/` (RAG over pgvector). Every sentence must cite a source chunk; a grounding check flags anything unsupported. | Approve / reject each draft |
| **5 Agent** | LangGraph runs discover → diagnose → opportunities → draft, then **pauses for review**, then plans experiments. Progress is checkpointed in Postgres so it can resume. | Required before anything is approved |
| **6 Experiments** | Re-asks the affected prompts after a change and compares with the baseline: change, 95% CI, p-value. A *repeat baseline* measures normal run-to-run noise. Always labelled **observational**. | Plan and run each re-test |

## 📊 Dashboard

A Next.js dashboard (`web/`) talks to a small FastAPI backend (`src/api/`) that wraps the same engines. Slow or billed work (discovery, measuring, drafting, the agent, re-tests) runs as a background job with live progress. Light and dark mode.

| Page | What you see and do |
|---|---|
| Overview | A sentence written from your latest data, share of voice per engine as brand swatches, trend, by-engine bars, category heatmap, biggest gaps, pipeline, run costs |
| 1 Ask the engines | **Ask your own question** and compare the engines' answers side by side (brands highlighted, sources listed, measured automatically), re-ask earlier questions; or tick questions from the fixed panel one by one or a whole category at a time |
| 2 Measure visibility | Mention rate, share of voice, list position, by category; most-cited sites and source types; every answer with brands highlighted and its sources; stability and fact accuracy; **Download PDF report** for the selected run (brand comparison with 95% intervals, gaps found, every answer) |
| 3 Find gaps | Ranked gaps with confidence, effort, Sephora vs benchmark, the evidence answers, approve/reject the action |
| 4 Draft content | Approved knowledge base, write a grounded draft for a gap, grounding check, sources, approve/reject |
| 5 Run the agent | Start the full loop on existing runs or new ones, step timeline, review drafts when it pauses, report |
| 6 Re-test | Plan a noise check or a change test, run it, baseline vs re-test with 95% CI and p-value |
| Check accuracy | **Download evaluation PDF** (every sandbox test with charts, expected-vs-actual tables, sign-off boxes); human labels vs the system: precision, recall, F1, labeller agreement |

The old Streamlit pages in `app/` still work as a fallback.

## 📁 Project structure

```
├── web/                  Next.js dashboard (App Router, Tailwind, shadcn/ui, Recharts)
├── app/                  Streamlit UI (fallback)
├── configs/              Project config: brands, aliases, providers (beauty_india.yaml)
├── data/
│   ├── raw/              Raw API responses (git-ignored)
│   └── reference/        Versioned reference data (prompts, domains, products, verified facts)
├── db/migrations/        SQL migrations (001 → 004)
├── docs/                 Architecture, data dictionary, decision / cost / meeting logs, model card
├── notebooks/            Exploration
├── reports/              Deliverables D1–D7 and final report
├── scripts/              CLI tools for every engine, the agent and experiments
├── src/
│   ├── config.py         Typed settings from .env + YAML
│   ├── db.py             Postgres connection + migration runner
│   ├── discovery/        Ask AI engines, store raw answers  ✅ built
│   │                     (models, providers, panel, repository, runner)
│   ├── diagnostics/      Parse mentions & citations, compute metrics  ✅ built
│   ├── opportunities/    Detect gaps, rank recommendations  ✅ built
│   ├── copilot/          RAG knowledge base + grounded drafts  ✅ built
│   ├── experimentation/  Baseline vs re-test analysis  ✅ built
│   ├── agent/            LangGraph orchestration  ✅ built
│   ├── api/              FastAPI backend for the dashboard (+ background jobs)
│   ├── services.py       Wires each engine to Postgres (agent, UI, CLI)
│   └── reporting.py      Dashboard queries
└── tests/                pytest suite (API calls mocked)
```

## 🗺️ Roadmap

- [x] **Phase 0**: Scaffold, config, DB schema, provider smoke test
- [x] **Discovery**: prompt panel → Perplexity, ChatGPT and Gemini → Bronze. First real run done on Gemini (30 prompts)
- [x] **Diagnostics**: visibility, accuracy, sources, repeatability, human validation (charter-complete)
- [x] **Opportunities**: 6 gap rules, confidence, effort, priority, evidence, approval
- [x] **Copilot**: RAG-grounded content drafting with grounding check and human approval
- [x] **Agent**: LangGraph orchestration of the full loop with a human-review pause
- [x] **Experimentation**: re-test, comparison with CI and p-value, noise baseline
- [x] **Dashboard & integration**: Next.js dashboard + FastAPI backend with live background jobs (Streamlit kept as fallback)
- [x] **Live database**: Supabase connected, migrations 001–007 applied, brands, prompts and domains loaded
- [ ] **Evaluation & delivery**: first real runs, human validation, D1–D7 / E1–E2 evidence, deployment

## 📏 Principles

- 🧾 **No invented data**: every metric and citation comes from a stored API response
- 🔗 **Full lineage**: derived records keep their source IDs
- 🏷️ **Versioned everything**: prompt panels, reference data, parsers, metrics and content
- 🔐 **No hard-coded secrets**: keys come from `.env` only
- ✅ **Tested engines**: every engine function has pytest coverage, with API calls mocked

## 📚 Documentation

| Doc | Purpose |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | System design |
| [DATA_DICTIONARY](docs/DATA_DICTIONARY.md) | Every table and column |
| [DECISION_LOG](docs/DECISION_LOG.md) | Why we chose what we chose |
| [COST_LOG](docs/COST_LOG.md) | API spend tracking |
| [MODEL_CARD](docs/MODEL_CARD.md) | Models used, limits, risks |
| [MEETING_LOG](docs/MEETING_LOG.md) | Team meetings |

---

<div align="center">

Built for the **XIME Analytics Capstone** · Pilot: Sephora India 🇮🇳

</div>
