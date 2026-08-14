"""Raw SQL used by PgVectorAdapter â€” kept in one module so the query shape
is reviewable independently of the adapter's control flow (NFR-MAINT.2).
"""
from __future__ import annotations

INSERT_CHUNK = """
    INSERT INTO document_chunks
        (company, project, source_doctype, source_name, file_id, content_hash,
         span_type, span_start, span_end, chunk_text)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING chunk_id;
"""

INSERT_EMBEDDING = """
    INSERT INTO embeddings (chunk_id, embedding, model_version)
    VALUES ($1, $2, $3)
    ON CONFLICT (chunk_id, model_version) DO UPDATE SET embedding = EXCLUDED.embedding;
"""

MARK_STALE = """
    UPDATE document_chunks
    SET is_stale = TRUE
    WHERE company = $1 AND source_doctype = $2 AND source_name = $3 AND is_stale = FALSE;
"""

SEARCH_BY_EMBEDDING = """
    SELECT
        c.chunk_id, c.company, c.project, c.source_doctype, c.source_name,
        c.span_type, c.span_start, c.span_end, c.chunk_text,
        1 - (e.embedding <=> $1) AS score
    FROM embeddings e
    JOIN document_chunks c ON c.chunk_id = e.chunk_id
    WHERE c.is_stale = FALSE
      AND c.company = $2
      AND ($3::text IS NULL OR c.project = $3)
    ORDER BY e.embedding <=> $1
    LIMIT $4;
"""
