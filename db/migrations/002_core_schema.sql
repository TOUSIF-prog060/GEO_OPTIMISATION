-- 002_core_schema: Bronze / Silver / Gold + opportunity, content and experiment tables.
-- Safe to run more than once (IF NOT EXISTS everywhere). Can be pasted into the
-- Supabase SQL editor or applied by src/db.py run_migrations().

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- ---------------------------------------------------------------- config
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS brands (
    brand_id   serial PRIMARY KEY,
    name       text NOT NULL UNIQUE,
    aliases    text[] NOT NULL DEFAULT '{}',
    market     text NOT NULL,
    is_target  boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompts (
    prompt_id     text PRIMARY KEY,
    text          text NOT NULL,
    category      text NOT NULL,
    intent        text NOT NULL,
    language      text NOT NULL DEFAULT 'en',
    panel_version text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (panel_version, text)
);
CREATE INDEX IF NOT EXISTS prompts_panel_version_idx ON prompts (panel_version);

CREATE TABLE IF NOT EXISTS domains (
    domain       text PRIMARY KEY,                -- e.g. nykaa.com (no www)
    domain_type  text NOT NULL CHECK (domain_type IN
                 ('brand_owned','competitor','retailer','editorial','ugc','video','other')),
    brand_id     int REFERENCES brands (brand_id),  -- set when brand_owned / competitor
    ref_version  text NOT NULL DEFAULT 'v1',
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- bronze (raw, never updated)
CREATE TABLE IF NOT EXISTS bronze_runs (
    run_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    panel_version   text NOT NULL,
    provider        text NOT NULL,                -- perplexity | openai
    model           text NOT NULL,
    config_snapshot jsonb NOT NULL DEFAULT '{}',  -- yaml config at run time
    run_type        text NOT NULL DEFAULT 'baseline' CHECK (run_type IN ('baseline','retest','adhoc')),
    status          text NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','failed','partial')),
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    notes           text
);

CREATE TABLE IF NOT EXISTS bronze_responses (
    response_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         uuid NOT NULL REFERENCES bronze_runs (run_id) ON DELETE CASCADE,
    prompt_id      text NOT NULL REFERENCES prompts (prompt_id),
    repeat_no      int  NOT NULL DEFAULT 1,       -- same prompt asked N times
    provider       text NOT NULL,
    model          text NOT NULL,
    request        jsonb NOT NULL,                -- exact payload sent
    raw_response   jsonb,                         -- exact payload received, untouched
    answer_text    text,
    input_tokens   int,
    output_tokens  int,
    cost_usd       numeric(12,6),
    latency_ms     int,
    http_status    int,
    error          text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, prompt_id, repeat_no)
);
CREATE INDEX IF NOT EXISTS bronze_responses_run_idx    ON bronze_responses (run_id);
CREATE INDEX IF NOT EXISTS bronze_responses_prompt_idx ON bronze_responses (prompt_id);

-- ---------------------------------------------------------------- silver (parsed facts)
CREATE TABLE IF NOT EXISTS silver_citations (
    citation_id  bigserial PRIMARY KEY,
    response_id  uuid NOT NULL REFERENCES bronze_responses (response_id) ON DELETE CASCADE,
    run_id       uuid NOT NULL REFERENCES bronze_runs (run_id) ON DELETE CASCADE,
    position     int  NOT NULL,                   -- order in the citation list, 1-based
    url          text NOT NULL,
    domain       text NOT NULL,
    title        text,
    parser_version text NOT NULL DEFAULT 'v1',
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (response_id, position, parser_version)
);
CREATE INDEX IF NOT EXISTS silver_citations_domain_idx ON silver_citations (domain);
CREATE INDEX IF NOT EXISTS silver_citations_run_idx    ON silver_citations (run_id);

CREATE TABLE IF NOT EXISTS silver_brand_mentions (
    mention_id      bigserial PRIMARY KEY,
    response_id     uuid NOT NULL REFERENCES bronze_responses (response_id) ON DELETE CASCADE,
    run_id          uuid NOT NULL REFERENCES bronze_runs (run_id) ON DELETE CASCADE,
    brand_id        int  NOT NULL REFERENCES brands (brand_id),
    mentioned       boolean NOT NULL,
    mention_count   int  NOT NULL DEFAULT 0,
    first_char_pos  int,                          -- where in answer_text it first appears
    rank_in_list    int,                          -- position if the answer is a ranked list
    is_recommended  boolean,
    sentiment       text CHECK (sentiment IN ('positive','neutral','negative','mixed')),
    snippet         text,                         -- matched text, for audit
    parser_version  text NOT NULL DEFAULT 'v1',
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (response_id, brand_id, parser_version)
);
CREATE INDEX IF NOT EXISTS silver_mentions_run_brand_idx ON silver_brand_mentions (run_id, brand_id);

CREATE TABLE IF NOT EXISTS silver_response_chunks (
    chunk_id     bigserial PRIMARY KEY,
    response_id  uuid NOT NULL REFERENCES bronze_responses (response_id) ON DELETE CASCADE,
    chunk_no     int  NOT NULL,
    chunk_text   text NOT NULL,
    embedding    vector(1536),                    -- text-embedding-3-small size
    embed_model  text,
    UNIQUE (response_id, chunk_no)
);
CREATE INDEX IF NOT EXISTS silver_chunks_embedding_idx
    ON silver_response_chunks USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------- gold (metrics)
CREATE TABLE IF NOT EXISTS gold_visibility (
    run_id           uuid NOT NULL REFERENCES bronze_runs (run_id) ON DELETE CASCADE,
    brand_id         int  NOT NULL REFERENCES brands (brand_id),
    category         text NOT NULL,               -- 'ALL' for the overall row
    n_responses      int  NOT NULL,
    mention_rate     numeric(6,4),                -- share of responses mentioning brand
    share_of_voice   numeric(6,4),                -- brand mentions / all tracked brand mentions
    avg_rank         numeric(6,2),
    citation_share   numeric(6,4),                -- citations to brand-owned domains / all citations
    positive_rate    numeric(6,4),
    metric_version   text NOT NULL DEFAULT 'v1',
    computed_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, brand_id, category, metric_version)
);

CREATE TABLE IF NOT EXISTS gold_source_share (
    run_id          uuid NOT NULL REFERENCES bronze_runs (run_id) ON DELETE CASCADE,
    category        text NOT NULL,
    domain          text NOT NULL,
    domain_type     text,
    n_citations     int  NOT NULL,
    citation_share  numeric(6,4),
    metric_version  text NOT NULL DEFAULT 'v1',
    computed_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, category, domain, metric_version)
);

-- ---------------------------------------------------------------- diagnose / recommend
CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          uuid NOT NULL REFERENCES bronze_runs (run_id),
    brand_id        int  NOT NULL REFERENCES brands (brand_id),
    prompt_id       text REFERENCES prompts (prompt_id),
    category        text,
    gap_type        text NOT NULL,                -- e.g. not_mentioned, low_rank, not_cited, negative
    severity        numeric(5,2),
    evidence_response_ids uuid[] NOT NULL DEFAULT '{}',
    details         jsonb NOT NULL DEFAULT '{}',
    status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','tested','closed')),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id    uuid NOT NULL REFERENCES opportunities (opportunity_id) ON DELETE CASCADE,
    action            text NOT NULL,
    rationale         text,
    priority          int,
    generated_by      text,                       -- rule id or model name
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- content + experiments
CREATE TABLE IF NOT EXISTS content_variants (
    variant_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id    uuid REFERENCES opportunities (opportunity_id),
    recommendation_id uuid REFERENCES recommendations (recommendation_id),
    version           int  NOT NULL DEFAULT 1,
    title             text,
    body              text NOT NULL,
    generated_by      text,                       -- model name
    embedding         vector(1536),
    status            text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','published','rejected')),
    published_url     text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (opportunity_id, version)
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    variant_id      uuid REFERENCES content_variants (variant_id),
    hypothesis      text NOT NULL,
    baseline_run_id uuid NOT NULL REFERENCES bronze_runs (run_id),
    retest_run_id   uuid REFERENCES bronze_runs (run_id),
    prompt_ids      text[] NOT NULL DEFAULT '{}',
    status          text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','running','done')),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS experiment_results (
    experiment_id   uuid NOT NULL REFERENCES experiments (experiment_id) ON DELETE CASCADE,
    brand_id        int  NOT NULL REFERENCES brands (brand_id),
    metric          text NOT NULL,                -- e.g. mention_rate
    baseline_value  numeric,
    retest_value    numeric,
    delta           numeric,
    p_value         numeric,
    computed_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (experiment_id, brand_id, metric)
);

-- Keep the Python migration runner in sync when this is pasted into the SQL editor.
INSERT INTO schema_migrations (filename) VALUES ('001_init.sql'), ('002_core_schema.sql')
ON CONFLICT DO NOTHING;
