-- 007_agent_experiments: agent run tracking + experimentation lab fields.
-- LangGraph's own checkpoint tables are created by PostgresSaver.setup() (src/agent/runner.py).

CREATE TABLE IF NOT EXISTS agent_runs (
    thread_id    text PRIMARY KEY,
    status       text NOT NULL CHECK (status IN ('running','awaiting_review','completed','failed')),
    params       jsonb NOT NULL DEFAULT '{}',
    summary      jsonb NOT NULL DEFAULT '{}',
    last_node    text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE experiments ADD COLUMN IF NOT EXISTS design text NOT NULL DEFAULT 'content_variant'
    CHECK (design IN ('content_variant','repeat_baseline'));
ALTER TABLE experiments ADD COLUMN IF NOT EXISTS opportunity_id uuid REFERENCES opportunities (opportunity_id);
ALTER TABLE experiments ADD COLUMN IF NOT EXISTS metric text NOT NULL DEFAULT 'mention_rate';
ALTER TABLE experiments ADD COLUMN IF NOT EXISTS created_by text;
ALTER TABLE experiments ADD COLUMN IF NOT EXISTS notes text;
ALTER TABLE experiments ADD COLUMN IF NOT EXISTS completed_at timestamptz;

ALTER TABLE experiment_results ADD COLUMN IF NOT EXISTS n_baseline int;
ALTER TABLE experiment_results ADD COLUMN IF NOT EXISTS n_retest int;
ALTER TABLE experiment_results ADD COLUMN IF NOT EXISTS ci_low numeric;
ALTER TABLE experiment_results ADD COLUMN IF NOT EXISTS ci_high numeric;
ALTER TABLE experiment_results ADD COLUMN IF NOT EXISTS interpretation text;

INSERT INTO schema_migrations (filename) VALUES ('007_agent_experiments.sql') ON CONFLICT DO NOTHING;
