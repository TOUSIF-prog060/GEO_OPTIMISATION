-- 005_opportunities: opportunity scoring (charter: evidence, severity, confidence, effort,
-- priority, validation approach) and human approval of recommendations.
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS title text;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS rationale text;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS validation_approach text;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS confidence numeric(4,3);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS effort text CHECK (effort IN ('low','medium','high'));
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS priority_score numeric(6,2);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS metric_name text;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS target_value numeric;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS benchmark_value numeric;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS benchmark_brand_id int REFERENCES brands (brand_id);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS dedupe_key text;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS rule_version text NOT NULL DEFAULT 'v1';
CREATE UNIQUE INDEX IF NOT EXISTS opportunities_dedupe_idx
    ON opportunities (run_id, dedupe_key, rule_version);

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'proposed'
    CHECK (status IN ('proposed','approved','rejected'));
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS reviewed_by text;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS review_notes text;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS evidence_response_ids uuid[] NOT NULL DEFAULT '{}';
CREATE UNIQUE INDEX IF NOT EXISTS recommendations_opp_gen_idx
    ON recommendations (opportunity_id, generated_by);

INSERT INTO schema_migrations (filename) VALUES ('005_opportunities.sql') ON CONFLICT DO NOTHING;
