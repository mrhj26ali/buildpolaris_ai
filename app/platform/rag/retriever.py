"""Retriever â€” runs vector search per reformulated query plus a graph
traversal, in parallel (ARCH Flowchart 4 step G: "Hybrid retrieval: vector
search + graph traversal"), producing the ranked lists RRF then fuses.
"""
from __future__ import annotations

import asyncio

from app.observability.logging import get_logger
from app.platform.graph_store.adapter import GraphResult, GraphStoreAdapter
from app.platform.rag.embedder import Embedder
from app.platform.vector_store.adapter import ScoredChunk, VectorStoreAdapter

logger = get_logger(__name__)


class Retriever:
    def __init__(
        self, vector_store: VectorStoreAdapter, graph_store: GraphStoreAdapter, embedder: Embedder,
    ) -> None:
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._embedder = embedder

    async def vector_search_many(
        self, queries: list[str], company: str, project: str | None, limit_per_query: int,
    ) -> list[list[ScoredChunk]]:
        embeddings = await self._embedder.embed_batch(queries)
        results = await asyncio.gather(
            *[
                self._vector_store.search(emb, company, project, limit_per_query)
                for emb in embeddings
            ]
        )
        return list(results)

    async def graph_enrich(
        self, seed_chunks: list[ScoredChunk], company: str, limit: int,
    ) -> list[GraphResult]:
        """Uses the top vector hits' source documents as seeds for a graph
        traversal, so retrieval can surface e.g. the Task an RFI blocks
        even when the traversal query itself never mentions that Task by
        name (FR-8.2's cross-cutting example).
        """
        if not seed_chunks:
            return []

        from app.platform.graph_store.cypher_queries import (
            DELAYED_TASK_SUBCONTRACTORS_WITH_INCIDENTS,
        )

        try:
            return await self._graph_store.traverse(
                DELAYED_TASK_SUBCONTRACTORS_WITH_INCIDENTS, {}, company, limit
            )
        except Exception as exc:  # noqa: BLE001 â€” graph enrichment is additive, never blocking
            logger.warning("graph_enrich_failed_continuing_vector_only", error=str(exc))
            return []
