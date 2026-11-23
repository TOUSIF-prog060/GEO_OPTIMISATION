-- 006_copilot: approved knowledge base (RAG over pgvector) and grounded content variants.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_documents (
    doc_id        text PRIMARY KEY,                 -- file name without extension
    title         text NOT NULL,
    source_url    text NOT NULL,
    verified_at   date NOT NULL,
    content_sha   text NOT NULL,                    -- re-embed only when the text changes
    ref_version   text NOT NULL DEFAULT 'v1',
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id      bigserial PRIMARY KEY,
    doc_id        text NOT NULL REFERENCES kb_documents (doc_id) ON DELETE CASCADE,
    chunk_no      int  NOT NULL,
    text          text NOT NULL,
    embedding     vector(1536) NOT NULL,
    embed_model   text NOT NULL,
    UNIQUE (doc_id, chunk_no)
);
CREATE INDEX IF NOT EXISTS kb_chunks_embedding_idx
    ON kb_chunks USING hnsw (embedding vector_cosine_ops);

ALTER TABLE content_variants ADD COLUMN IF NOT EXISTS content_type text;
ALTER TABLE content_variants ADD COLUMN IF NOT EXISTS source_chunk_ids bigint[] NOT NULL DEFAULT '{}';
ALTER TABLE content_variants ADD COLUMN IF NOT EXISTS retrieved_chunk_ids bigint[] NOT NULL DEFAULT '{}';
ALTER TABLE content_variants ADD COLUMN IF NOT EXISTS evidence_response_ids uuid[] NOT NULL DEFAULT '{}';
ALTER TABLE content_variants ADD COLUMN IF NOT EXISTS grounding jsonb NOT NULL DEFAULT '{}';
ALTER TABLE content_variants ADD COLUMN IF NOT EXISTS reviewed_by text;
ALTER TABLE content_variants ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;
ALTER TABLE content_variants ADD COLUMN IF NOT EXISTS review_notes text;

INSERT INTO schema_migrations (filename) VALUES ('006_copilot.sql') ON CONFLICT DO NOTHING;
