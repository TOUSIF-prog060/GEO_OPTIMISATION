# Data Dictionary

## brands (config) — migration 001
| column | type | notes |
|---|---|---|
| brand_id | serial PK | |
| name | text, unique | |
| aliases | text[] | strings used for mention matching |
| market | text | e.g. IN |
| is_target | boolean | exactly one target per project |
| created_at | timestamptz | |

## prompts (config) — migration 001
| column | type | notes |
|---|---|---|
| prompt_id | text PK | stable id from the panel CSV |
| text | text | |
| category | text | |
| intent | text | |
| language | text | default en |
| panel_version | text | e.g. v1 |
| created_at | timestamptz | |
Unique on (panel_version, text).

## schema_migrations (system)
| column | type | notes |
|---|---|---|
| filename | text PK | migration file applied |
| applied_at | timestamptz | |

---
# Migration 002 — core schema
Lineage rule: every Silver/Gold/derived row carries `run_id` and/or `response_id`.
Parsed and computed rows carry a version column (`parser_version`, `metric_version`, `version`).

## domains (config)
| column | type | notes |
|---|---|---|
| domain | text PK | bare domain, no www |
| domain_type | text | brand_owned, competitor, retailer, editorial, ugc, video, other |
| brand_id | int FK brands | set for brand-owned / competitor domains |
| ref_version | text | reference data version |

## bronze_runs
| column | type | notes |
|---|---|---|
| run_id | uuid PK | |
| panel_version | text | prompt panel used |
| provider, model | text | |
| config_snapshot | jsonb | config at run time |
| run_type | text | baseline, retest, adhoc |
| status | text | running, completed, failed, partial |
| started_at, finished_at | timestamptz | |

## bronze_responses (raw, never updated)
| column | type | notes |
|---|---|---|
| response_id | uuid PK | |
| run_id | uuid FK | |
| prompt_id | text FK | |
| repeat_no | int | repeat index; unique (run_id, prompt_id, repeat_no) |
| request / raw_response | jsonb | exact payloads |
| answer_text | text | |
| input_tokens, output_tokens, cost_usd, latency_ms, http_status, error | | call metadata |

## silver_citations
response_id, run_id, position (1-based), url, domain, title, parser_version. Unique (response_id, position, parser_version).

## silver_brand_mentions
response_id, run_id, brand_id, mentioned, mention_count, first_char_pos, rank_in_list, is_recommended, sentiment (positive/neutral/negative/mixed), snippet, parser_version. Unique (response_id, brand_id, parser_version).

## silver_response_chunks
response_id, chunk_no, chunk_text, embedding vector(1536) (HNSW cosine index), embed_model.

## gold_visibility
PK (run_id, brand_id, category, metric_version). n_responses, mention_rate, share_of_voice, avg_rank, citation_share, positive_rate. category = 'ALL' for the overall row.

## gold_source_share
PK (run_id, category, domain, metric_version). domain_type, n_citations, citation_share.

## opportunities
opportunity_id uuid PK, run_id, brand_id, prompt_id, category, gap_type, severity, evidence_response_ids uuid[], details jsonb, status (open/in_progress/tested/closed).

## recommendations
recommendation_id uuid PK, opportunity_id FK, action, rationale, priority, generated_by.

## content_variants
variant_id uuid PK, opportunity_id, recommendation_id, version (unique per opportunity), title, body, generated_by, embedding vector(1536), status (draft/approved/published/rejected), published_url.

## experiments
experiment_id uuid PK, variant_id, hypothesis, baseline_run_id, retest_run_id, prompt_ids text[], status (planned/running/done).

## experiment_results
PK (experiment_id, brand_id, metric). baseline_value, retest_value, delta, p_value.
