-- ERD v2.1 Â§4.2 â€” text/provenance half of the retrieval unit. Split from
-- the embedding vector (0004) so a re-embed for a new model version never
-- requires re-parsing/re-chunking the source document (NFR-AIGOV.2).
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company         TEXT NOT NULL,          -- tenant isolation (NFR-SEC.8)
    project         TEXT NOT NULL,
    source_doctype  TEXT NOT NULL,          -- 'Commitment' | 'Submittal Package' | 'RFI'
    source_name     TEXT NOT NULL,          -- MariaDB document name â€” the citation's human-meaningful anchor
    file_id         TEXT NOT NULL,          -- MariaDB File.name
    content_hash    TEXT NOT NULL,          -- matches AI Document Index.content_hash (idempotency join key)
    span_type       TEXT NOT NULL CHECK (span_type IN ('page', 'clause')),
    span_start      INT  NOT NULL,
    span_end        INT  NOT NULL,
    chunk_text      TEXT NOT NULL,
    is_stale        BOOLEAN NOT NULL DEFAULT FALSE,  -- set on re-ingest (UC-8.4 A1); never hard-deleted mid-query
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chunks_scope_idx  ON document_chunks (company, project, is_stale);
CREATE INDEX IF NOT EXISTS chunks_source_idx ON document_chunks (source_doctype, source_name);
CREATE INDEX IF NOT EXISTS chunks_hash_idx   ON document_chunks (content_hash);
