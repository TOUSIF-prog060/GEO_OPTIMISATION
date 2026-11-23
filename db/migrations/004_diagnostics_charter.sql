-- 004_diagnostics_charter: complete Phase 2 against charter v2.0.
-- Product catalogue + verified facts, product mentions, accuracy checks, repeatability,
-- extraction method / confidence on mentions, citation relevance review, human validation.
-- Safe to run more than once.

-- ---------------------------------------------------------------- reference (versioned)
CREATE TABLE IF NOT EXISTS products (
    product_id        text PRIMARY KEY,                -- stable id from products_<v>.csv
    product_name      text NOT NULL,
    maker             text,                            -- manufacturer brand, e.g. "Fenty Beauty"
    aliases           text[] NOT NULL DEFAULT '{}',
    category          text NOT NULL,
    source_url        text NOT NULL,                   -- where the details were verified
    last_verified_at  date NOT NULL,
    ref_version       text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reference_facts (
    fact_id           text PRIMARY KEY,                -- stable id from reference_facts_<v>.csv
    subject_type      text NOT NULL CHECK (subject_type IN ('brand','product')),
    subject           text NOT NULL,                   -- brand name or product_id
    attribute         text NOT NULL,                   -- e.g. price_inr, spf, offers_cod
    approved_value    text NOT NULL,
    value_type        text NOT NULL CHECK (value_type IN ('text','number','boolean')),
    tolerance         numeric,                         -- numbers: allowed relative difference
    source_url        text NOT NULL,
    last_verified_at  date NOT NULL,
    ref_version       text NOT NULL,
    UNIQUE (subject_type, subject, attribute, ref_version)
);

-- ---------------------------------------------------------------- silver additions
ALTER TABLE silver_brand_mentions ADD COLUMN IF NOT EXISTS extraction_method text NOT NULL DEFAULT 'alias_rule';
ALTER TABLE silver_brand_mentions ADD COLUMN IF NOT EXISTS confidence numeric(4,3);  -- NULL for deterministic rules

ALTER TABLE silver_citations ADD COLUMN IF NOT EXISTS relevance_review text
    CHECK (relevance_review IN ('relevant','partly_relevant','not_relevant'));
ALTER TABLE silver_citations ADD COLUMN IF NOT EXISTS reviewed_by text;
ALTER TABLE silver_citations ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;

CREATE TABLE IF NOT EXISTS silver_product_mentions (
    product_mention_id bigserial PRIMARY KEY,
    response_id        uuid NOT NULL REFERENCES bronze_responses (response_id) ON DELETE CASCADE,
    run_id             uuid NOT NULL REFERENCES bronze_runs (run_id) ON DELETE CASCADE,
    product_id         text NOT NULL REFERENCES products (product_id),
    mention_count      int  NOT NULL,
    first_char_pos     int,
    rank_in_list       int,
    snippet            text,
    extraction_method  text NOT NULL DEFAULT 'alias_rule',
    confidence         numeric(4,3),
    parser_version     text NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (response_id, product_id, parser_version)
);
CREATE INDEX IF NOT EXISTS silver_product_mentions_run_idx ON silver_product_mentions (run_id);

CREATE TABLE IF NOT EXISTS silver_accuracy_checks (
    check_id          bigserial PRIMARY KEY,
    response_id       uuid NOT NULL REFERENCES bronze_responses (response_id) ON DELETE CASCADE,
    run_id            uuid NOT NULL REFERENCES bronze_runs (run_id) ON DELETE CASCADE,
    fact_id           text NOT NULL REFERENCES reference_facts (fact_id),
    stated_value      text,                            -- what the AI answer claimed (NULL = not stated)
    approved_value    text NOT NULL,                   -- copied at check time, for audit
    verdict           text NOT NULL CHECK (verdict IN ('match','mismatch','not_mentioned','unverifiable')),
    extraction_method text NOT NULL,                   -- e.g. 'llm_extract'
    extracted_by      text,                            -- model name
    checker_version   text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (response_id, fact_id, checker_version)
);
CREATE INDEX IF NOT EXISTS silver_accuracy_run_idx ON silver_accuracy_checks (run_id);

-- ---------------------------------------------------------------- gold additions
CREATE TABLE IF NOT EXISTS gold_repeatability (
    run_id                 uuid NOT NULL REFERENCES bronze_runs (run_id) ON DELETE CASCADE,
    brand_id               int  NOT NULL REFERENCES brands (brand_id),
    n_prompts              int  NOT NULL,              -- prompts asked 2+ times
    agreement_rate         numeric(6,4),               -- share of prompts where all repeats agree
    mean_within_prompt_sd  numeric(6,4),               -- mean SD of 0/1 mention across repeats
    metric_version         text NOT NULL,
    computed_at            timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, brand_id, metric_version)
);

CREATE TABLE IF NOT EXISTS gold_accuracy (
    run_id           uuid NOT NULL REFERENCES bronze_runs (run_id) ON DELETE CASCADE,
    subject          text NOT NULL,
    attribute        text NOT NULL,
    n_checked        int  NOT NULL,
    n_match          int  NOT NULL,
    n_mismatch       int  NOT NULL,
    n_not_mentioned  int  NOT NULL,
    n_unverifiable   int  NOT NULL,
    accuracy_rate    numeric(6,4),                     -- match / (match + mismatch)
    metric_version   text NOT NULL,
    computed_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, subject, attribute, metric_version)
);

-- ---------------------------------------------------------------- human validation
CREATE TABLE IF NOT EXISTS validation_samples (
    sample_version  text NOT NULL,
    response_id     uuid NOT NULL REFERENCES bronze_responses (response_id) ON DELETE CASCADE,
    stratum         text,                              -- provider|category used for sampling
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sample_version, response_id)
);

CREATE TABLE IF NOT EXISTS validation_labels (
    label_id        bigserial PRIMARY KEY,
    sample_version  text NOT NULL,
    response_id     uuid NOT NULL REFERENCES bronze_responses (response_id) ON DELETE CASCADE,
    brand_id        int  NOT NULL REFERENCES brands (brand_id),
    labeller        text NOT NULL,                     -- initials, e.g. "TS"
    mentioned       boolean NOT NULL,
    rank_in_list    int,
    sentiment       text CHECK (sentiment IN ('positive','neutral','negative','mixed')),
    is_recommended  boolean,
    notes           text,
    labelled_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (sample_version, response_id, brand_id, labeller)
);

INSERT INTO schema_migrations (filename) VALUES ('004_diagnostics_charter.sql')
ON CONFLICT DO NOTHING;
