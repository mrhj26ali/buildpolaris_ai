"""VectorStoreAdapter â€” the half of RetrievalAdapter (ERD Â§4.4) concerned
with similarity search. NFR-EXT.2: the underlying store must be swappable
without touching RagService â€” this port is that seam.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class ScoredChunk:
    chunk_id: str
    company: str
    project: str
    source_doctype: str
    source_name: str
    span_type: str
    span_start: int
    span_end: int
    chunk_text: str
    score: float  # similarity score, higher is better (1 - cosine distance)


@runtime_checkable
class VectorStoreAdapter(Protocol):
    async def upsert_chunk(
        self, company: str, project: str, source_doctype: str, source_name: str,
        file_id: str, content_hash: str, span_type: str, span_start: int, span_end: int,
        chunk_text: str, embedding: list[float], model_version: str,
    ) -> str:
        """Insert one chunk + its embedding; returns chunk_id."""
        ...

    async def mark_stale(self, company: str, source_doctype: str, source_name: str) -> int:
        """UC-8.4 A1 â€” mark prior chunks stale (never hard-delete mid-query)
        ahead of a re-ingest. Returns the number of rows marked."""
        ...

    async def search(
        self, query_embedding: list[float], company: str, project: str | None,
        limit: int = 10,
    ) -> list[ScoredChunk]:
        """Cosine-similarity search, scoped to tenant/Project (NFR-SEC.8),
        filtered to is_stale = false."""
        ...
