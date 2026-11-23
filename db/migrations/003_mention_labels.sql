-- 003_mention_labels: record who labelled sentiment / is_recommended on a mention, and when.
ALTER TABLE silver_brand_mentions ADD COLUMN IF NOT EXISTS classified_by text;
ALTER TABLE silver_brand_mentions ADD COLUMN IF NOT EXISTS classified_at timestamptz;

INSERT INTO schema_migrations (filename) VALUES ('003_mention_labels.sql')
ON CONFLICT DO NOTHING;
