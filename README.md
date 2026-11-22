<div align="center">

# 🔍 Beyond the Search Bar

### AI Discovery Intelligence Platform (GEO)

**How do AI answer engines talk about your brand, and what can you do about it?**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Supabase](https://img.shields.io/badge/DB-Supabase%20Postgres-3ECF8E?logo=supabase&logoColor=white)
![pgvector](https://img.shields.io/badge/Vectors-pgvector-336791?logo=postgresql&logoColor=white)
![LangGraph](https://img.shields.io/badge/Agent-LangGraph-1C3C3C)
![Status](https://img.shields.io/badge/status-pilot%20in%20progress-orange)

*XIME Analytics Capstone · Team of 3*

</div>

---

## ✨ What it does

People increasingly ask **ChatGPT, Perplexity and other AI engines** what to buy instead of typing into a search bar. This means brands need a new kind of optimisation: **Generative Engine Optimisation (GEO)**.

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
| **AI engines** | Perplexity Sonar · OpenAI (web search) |

## 🏗️ Architecture

```
app/  (Streamlit UI)        src/agent/  (LangGraph)
          │                        │
          └──────────┬─────────────┘
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
#   then fill in SUPABASE_DB_URL, PERPLEXITY_API_KEY, OPENAI_API_KEY

# 4. Database
python -m src.db                # applies db/migrations/*.sql
#   (or paste db/migrations/002_core_schema.sql into the Supabase SQL editor)

# 5. Run
streamlit run app/Home.py
```

> 💸 `python scripts/smoke_test_providers.py` sends **one real, billed** question to each AI engine. Use it to confirm your keys work.

## 🧰 Commands

| Task | Command |
|---|---|
| Run the app | `streamlit run app/Home.py` |
| Tests | `pytest -q` |
| Lint & format | `ruff check . && ruff format .` |
| Apply migrations | `python -m src.db` |
| Provider smoke test | `python scripts/smoke_test_providers.py` |

## 📁 Project structure

```
├── app/                  Streamlit UI (Home.py + pages/)
├── configs/              Project config: brands, aliases, providers (beauty_india.yaml)
├── data/
│   ├── raw/              Raw API responses (git-ignored)
│   └── reference/        Versioned reference data
├── db/migrations/        SQL migrations (001_init, 002_core_schema)
├── docs/                 Architecture, data dictionary, decision / cost / meeting logs, model card
├── notebooks/            Exploration
├── reports/              Deliverables D1–D7 and final report
├── scripts/              One-off utilities (provider smoke test)
├── src/
│   ├── config.py         Typed settings from .env + YAML
│   ├── db.py             Postgres connection + migration runner
│   ├── discovery/        Ask AI engines, store raw answers
│   ├── diagnostics/      Parse mentions & citations, compute metrics
│   ├── opportunities/    Detect gaps, rank recommendations
│   ├── copilot/          Draft content variants
│   ├── experimentation/  Baseline vs re-test analysis
│   └── agent/            LangGraph orchestration
└── tests/                pytest suite (API calls mocked)
```

## 🗺️ Roadmap

- [x] **Phase 0**: Scaffold, config, DB schema, provider smoke test
- [ ] **Discovery**: run the prompt panel across both engines → Bronze
- [ ] **Diagnostics**: mention & citation parsing → Silver / Gold metrics
- [ ] **Opportunities**: gap detection & recommendations
- [ ] **Copilot**: versioned content drafting
- [ ] **Experimentation**: re-test & uplift measurement
- [ ] **Agent**: LangGraph orchestration of the full loop
- [ ] **Dashboard**: Plotly visual analytics in Streamlit

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
