-- ERD v2.1 Â§4.2 â€” the vector half. embedding dimension is pinned per
-- ERD Â§8.1 (open decision #1) to the sentence-transformers all-MiniLM-L6-v2
-- default (384-dim, free/local). Changing it is a documented backfill, not
-- a silent migration (ERD Â§7).
CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id        UUID NOT NULL REFERENCES document_chunks(chunk_id) ON DELETE CASCADE,
    embedding       vector(384) NOT NULL,
    model_version   TEXT NOT NULL,          -- NFR-AIGOV.2: version-pinned, never "latest"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chunk_id, model_version)
);

CREATE INDEX IF NOT EXISTS embeddings_hnsw_idx
    ON embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS embeddings_chunk_idx ON embeddings (chunk_id);
