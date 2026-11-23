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

---
# Migration 003 — mention labels
## silver_brand_mentions (added columns)
| column | type | notes |
|---|---|---|
| classified_by | text | model that set `sentiment` / `is_recommended` (e.g. gpt-5-mini); NULL = not labelled |
| classified_at | timestamptz | when it was labelled |

# Reference data
## data/reference/domains_<version>.csv → `domains`
| column | notes |
|---|---|
| domain | bare host, no www (normalised on load) |
| domain_type | brand_owned, competitor, retailer, editorial, ugc, video, other |
| brand_name | required for brand_owned / competitor; resolved to `brand_id` on sync |
Subdomains inherit their parent's entry (`blog.nykaa.com` → `nykaa.com`). Cited domains not in the file show as `unclassified` in `gold_source_share`.

# Metric definitions (metric_version v1)
Per run × category (`ALL` = whole run); errored responses are excluded.
| metric | definition |
|---|---|
| mention_rate | responses mentioning the brand / responses |
| share_of_voice | responses mentioning the brand / sum of that count over all tracked brands |
| avg_rank | mean `rank_in_list` (1 = first top-level list item / heading naming the brand) |
| citation_share | citations to domains with this `brand_id` / all citations |
| positive_rate | mentions labelled positive / mentions with any label (NULL until labelled) |

# Parser rules (parser_version v1)
- Mention = whole-word, case-insensitive match on brand name or any alias; longest alias wins on overlap.
- One `silver_brand_mentions` row per brand per successful response, including `mentioned = false`.
- `rank_in_list`: top-level numbered/bulleted items and markdown headings only; nested items ignored.
- Citations: Perplexity `citations` (fallback `search_results`); OpenAI `url_citation` annotations; Gemini `groundingMetadata.groundingChunks` as `https://<title>` (the source domain; the redirect URIs in the raw payload expire). Deduped, in order.

---
# Migration 004 — diagnostics completed to charter v2.0

## products (reference) — from data/reference/products_<v>.csv
product_id PK · product_name · maker · aliases text[] · category · source_url (required) · last_verified_at date (required) · ref_version

## reference_facts (reference) — from data/reference/reference_facts_<v>.csv
fact_id PK · subject_type (brand | product) · subject (brand name or product_id) · attribute · approved_value · value_type (text | number | boolean) · tolerance (numbers only, relative) · source_url · last_verified_at · ref_version. Unique (subject_type, subject, attribute, ref_version).

## silver_brand_mentions (added)
| column | notes |
|---|---|
| extraction_method | `alias_rule` for parser v1; future ML/LLM extractors use their own name |
| confidence | NULL for deterministic rules; filled by probabilistic methods |

## silver_citations (added)
relevance_review (relevant | partly_relevant | not_relevant) · reviewed_by · reviewed_at. Filled by human review.

## silver_product_mentions
response_id · run_id · product_id · mention_count · first_char_pos · rank_in_list · snippet · extraction_method · confidence · parser_version. Only products that ARE mentioned get a row. Unique (response_id, product_id, parser_version).

## silver_accuracy_checks
response_id · run_id · fact_id · stated_value (what the answer claimed; NULL = not stated) · approved_value (copied at check time) · verdict (match | mismatch | not_mentioned | unverifiable) · extraction_method (`llm_extract`) · extracted_by (model) · checker_version. Only facts whose subject is mentioned in the answer are checked.

## gold_repeatability
PK (run_id, brand_id, metric_version). n_prompts (asked 2+ times) · agreement_rate · mean_within_prompt_sd.

## gold_accuracy
PK (run_id, subject, attribute, metric_version). n_checked · n_match · n_mismatch · n_not_mentioned · n_unverifiable · accuracy_rate = match / (match + mismatch).

## validation_samples / validation_labels (human validation)
- validation_samples: (sample_version, response_id) PK · stratum (provider|category).
- validation_labels: sample_version · response_id · brand_id · labeller · mentioned · rank_in_list · sentiment · is_recommended · notes. Unique (sample_version, response_id, brand_id, labeller).

# Comparison rules (checker_version v1)
- boolean: yes/true/available/offers vs no/false/not; "not available" = false; anything else = unverifiable.
- number: first number in the text (commas and ₹ ignored); match if |stated − approved| ≤ tolerance × approved (exact if no tolerance).
- text: match if every word of the approved value appears in the stated value; otherwise mismatch.

---
# Migration 005 — opportunities (Phase 3)
## opportunities (added)
title · rationale · validation_approach · confidence (0–1) · effort (low/medium/high) · priority_score · metric_name · target_value · benchmark_value · benchmark_brand_id · dedupe_key · rule_version. Unique (run_id, dedupe_key, rule_version): re-running updates scores but keeps `status`.
- gap_type: visibility_gap, ranking_gap, citation_gap, sentiment_gap, accuracy_issue, unstable_visibility
- priority_score = 100 × severity × confidence ÷ effort weight (low 1, medium 2, high 3)
- confidence = 1 − one-sided p-value (two-proportion z-test) for visibility/citation gaps; n/(n+10) otherwise
## recommendations (added)
status (proposed/approved/rejected) · reviewed_by · reviewed_at · review_notes · evidence_response_ids. Unique (opportunity_id, generated_by); re-running keeps the review decision. `generated_by = template_v1`.

# Migration 006 — content copilot (Phase 4)
## kb_documents
doc_id PK (file name) · title · source_url · verified_at · content_sha (re-embed only on change) · ref_version.
## kb_chunks
chunk_id PK · doc_id FK · chunk_no · text · embedding vector(1536) (HNSW cosine) · embed_model.
## content_variants (added)
content_type (faq/buying_guide/product_description/content_brief) · source_chunk_ids (cited) · retrieved_chunk_ids · evidence_response_ids · grounding jsonb {retrieved, cited, invalid_citations, unsupported_claims, needs_more_info, grounded} · reviewed_by · reviewed_at · review_notes. Status starts `draft`; only a human sets approved/rejected.

# Migration 007 — agent + experimentation (Phases 5–6)
## agent_runs
thread_id PK · status (running/awaiting_review/completed/failed) · params · summary · last_node · timestamps. LangGraph checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`) are created by `PostgresSaver.setup()`.
## experiments (added)
design (content_variant / repeat_baseline) · opportunity_id · metric · created_by · notes · completed_at.
## experiment_results (added)
n_baseline · n_retest · ci_low · ci_high (95% Wald CI of retest − baseline) · interpretation (always labelled observational).
