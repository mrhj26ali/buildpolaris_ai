"""Embedding worker â€” the chunk -> embed -> store stage (ARCH Flowchart 5
steps K/L/M). Split out from ingestion_service.py so it can be invoked as
a background task (FastAPI BackgroundTasks in v1; a real queue consumer
later without changing this function's signature) and unit-tested without
spinning up the HTTP layer.
"""
from __future__ import annotations

from app.observability.logging import get_logger
from app.platform.rag.chunker import RawChunk
from app.platform.rag.embedder import Embedder
from app.platform.vector_store.adapter import VectorStoreAdapter

logger = get_logger(__name__)


async def embed_and_store_chunks(
    chunks: list[RawChunk], company: str, project: str, source_doctype: str,
    source_name: str, file_id: str, content_hash: str,
    vector_store: VectorStoreAdapter, embedder: Embedder,
) -> int:
    if not chunks:
        return 0

    texts = [c.text for c in chunks]
    embeddings = await embedder.embed_batch(texts)

    stored = 0
    for chunk, embedding in zip(chunks, embeddings):
        await vector_store.upsert_chunk(
            company=company, project=project, source_doctype=source_doctype,
            source_name=source_name, file_id=file_id, content_hash=content_hash,
            span_type=chunk.span_type, span_start=chunk.span_start, span_end=chunk.span_end,
            chunk_text=chunk.text, embedding=embedding, model_version=embedder.model_version,
        )
        stored += 1

    logger.info(
        "chunks_embedded_and_stored", source_doctype=source_doctype, source_name=source_name,
        chunk_count=stored,
    )
    return stored
