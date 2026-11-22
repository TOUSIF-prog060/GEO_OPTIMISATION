-- 001_init: config tables. Applied by src/db.py run_migrations().

CREATE TABLE IF NOT EXISTS brands (
    brand_id   serial PRIMARY KEY,
    name       text NOT NULL UNIQUE,
    aliases    text[] NOT NULL DEFAULT '{}',
    market     text NOT NULL,
    is_target  boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompts (
    prompt_id     text PRIMARY KEY,          -- stable id from the panel CSV, e.g. SKN-001
    text          text NOT NULL,
    category      text NOT NULL,
    intent        text NOT NULL,
    language      text NOT NULL DEFAULT 'en',
    panel_version text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (panel_version, text)
);

CREATE INDEX IF NOT EXISTS prompts_panel_version_idx ON prompts (panel_version);
