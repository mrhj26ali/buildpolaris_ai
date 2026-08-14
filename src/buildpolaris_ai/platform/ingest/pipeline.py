"""Document ingestion pipeline: parse -> chunk -> embed -> store."""
from __future__ import annotations

import uuid
from typing import Any, Optional

import structlog

from buildpolaris_ai.platform.ingest.pdf_parser import PDFParser
from buildpolaris_ai.platform.retrieval.chunker import ConstructionChunker
from buildpolaris_ai.platform.embedding.service import get_embedding_service

logger = structlog.get_logger()


class IngestionPipeline:
    """Processes documents into embeddings and graph nodes."""

    def __init__(self, conn) -> None:
        self.conn = conn
        self.pdf_parser = PDFParser()
        self.chunker = ConstructionChunker(chunk_size=512, chunk_overlap=64)
        self.embedding_service = get_embedding_service()

    async def ingest_text(
        self,
        text: str,
        docname: str,
        doctype: str,
        tenant_id: str,
        project_id: str = "",
        metadata: dict | None = None,
    ) -> int:
        """Ingest plain text document. Returns number of chunks created."""
        chunks = self.chunker.chunk_text(
            text, docname=docname, doctype=doctype, metadata=metadata
        )

        if not chunks:
            return 0

        # Batch embed
        texts = [c.text for c in chunks]
        embeddings = await self.embedding_service.embed_batch(texts)

        # Store in pgvector
        from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
        vector_store = PgVectorAdapter(self.conn)

        stored = 0
        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{docname}:{chunk.chunk_index}"))
            chunk_meta = {
                **chunk.metadata,
                "docname": docname,
                "doctype": doctype,
                "chunk_index": chunk.chunk_index,
                "chunk_text": chunk.text[:500],
            }
            await vector_store.upsert_embedding(chunk_id, tenant_id, embedding, chunk_meta)
            stored += 1

        logger.info("Text ingested", docname=docname, chunks=stored)
        return stored

    async def ingest_pdf(
        self,
        file_path: str,
        docname: str,
        doctype: str,
        tenant_id: str,
        project_id: str = "",
        metadata: dict | None = None,
    ) -> int:
        """Ingest PDF document. Returns number of chunks created."""
        pages = self.pdf_parser.parse_file(file_path)
        if not pages:
            return 0

        chunks = self.chunker.chunk_pdf_text(
            pages, docname=docname, doctype=doctype, metadata=metadata
        )

        if not chunks:
            return 0

        texts = [c.text for c in chunks]
        embeddings = await self.embedding_service.embed_batch(texts)

        from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
        vector_store = PgVectorAdapter(self.conn)

        stored = 0
        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{docname}:{chunk.chunk_index}"))
            chunk_meta = {
                **chunk.metadata,
                "docname": docname,
                "doctype": doctype,
                "chunk_index": chunk.chunk_index,
                "chunk_text": chunk.text[:500],
            }
            await vector_store.upsert_embedding(chunk_id, tenant_id, embedding, chunk_meta)
            stored += 1

        logger.info("PDF ingested", docname=docname, chunks=stored)
        return stored

    async def ingest_cdc_event(self, event_payload: dict[str, Any], tenant_id: str) -> int:
        """Ingest a CDC event payload as a document chunk."""
        docname = event_payload.get("docname", "")
        doctype = event_payload.get("doctype", "")
        payload = event_payload.get("payload", {})

        # Build text from payload fields
        text_parts = []
        for key in ["description", "subject", "title", "notes", "extracted_text"]:
            if key in payload and payload[key]:
                text_parts.append(str(payload[key]))

        if not text_parts:
            text_parts.append(str(payload))

        text = f"Document ID: {docname}. Type: {doctype}. " + " ".join(text_parts)

        return await self.ingest_text(
            text=text,
            docname=docname,
            doctype=doctype,
            tenant_id=tenant_id,
            metadata=payload,
        )
