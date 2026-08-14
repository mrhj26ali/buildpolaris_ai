"""Reranker â€” optional, tenant-tunable (ARCH Â§3.3 point 6, config
`rag.reranker_enabled`). Off by default: a cross-encoder rerank pass adds
latency (NFR-PERF.6) for a corpus this size where RRF fusion already
performs adequately; it's a lever a tenant with a much larger document
set can flip on, not a hardcoded stage.
"""
from __future__ import annotations

from app.config import get_settings
from app.observability.logging import get_logger
from app.platform.vector_store.adapter import ScoredChunk

logger = get_logger(__name__)

_cross_encoder = None


async def rerank(query: str, chunks: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
    settings = get_settings().rag
    if not settings.reranker_enabled or not chunks:
        return chunks[:top_k]

    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder

        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        logger.info("reranker_model_loaded")

    import asyncio

    pairs = [(query, c.chunk_text) for c in chunks]
    loop = asyncio.get_event_loop()
    scores = await loop.run_in_executor(None, _cross_encoder.predict, pairs)

    reranked = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
    return [c for c, _score in reranked[:top_k]]
