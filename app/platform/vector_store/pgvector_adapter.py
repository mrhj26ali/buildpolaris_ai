"""PgVectorAdapter â€” concrete VectorStoreAdapter (ARCH Â§3.3 point 1).

A future migration off pgvector to a managed vector service happens
behind this one class; RagService and every agent never import asyncpg
or pgvector directly.
"""
from __future__ import annotations

import asyncpg

from app.observability.logging import get_logger
from app.platform.vector_store.adapter import ScoredChunk
from app.platform.vector_store.queries import (
    INSERT_CHUNK,
    INSERT_EMBEDDING,
    MARK_STALE,
    SEARCH_BY_EMBEDDING,
)

logger = get_logger(__name__)


class PgVectorAdapter:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def upsert_chunk(
        self, company: str, project: str, source_doctype: str, source_name: str,
        file_id: str, content_hash: str, span_type: str, span_start: int, span_end: int,
        chunk_text: str, embedding: list[float], model_version: str,
    ) -> str:
        async with self._conn.transaction():
            chunk_row = await self._conn.fetchrow(
                INSERT_CHUNK, company, project, source_doctype, source_name, file_id,
                content_hash, span_type, span_start, span_end, chunk_text,
            )
            chunk_id = chunk_row["chunk_id"]
            await self._conn.execute(INSERT_EMBEDDING, chunk_id, embedding, model_version)
        return str(chunk_id)

    async def mark_stale(self, company: str, source_doctype: str, source_name: str) -> int:
        result = await self._conn.execute(MARK_STALE, company, source_doctype, source_name)
        # asyncpg returns 'UPDATE <n>'
        return int(result.split()[-1])

    async def search(
        self, query_embedding: list[float], company: str, project: str | None,
        limit: int = 10,
    ) -> list[ScoredChunk]:
        rows = await self._conn.fetch(
            SEARCH_BY_EMBEDDING, query_embedding, company, project, limit
        )
        return [
            ScoredChunk(
                chunk_id=str(r["chunk_id"]), company=r["company"], project=r["project"],
                source_doctype=r["source_doctype"], source_name=r["source_name"],
                span_type=r["span_type"], span_start=r["span_start"], span_end=r["span_end"],
                chunk_text=r["chunk_text"], score=float(r["score"]),
            )
            for r in rows
        ]
