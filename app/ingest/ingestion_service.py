"""IngestionService Ã¢â‚¬â€ ARCH Flowchart 5, steps H onward (this sidecar's
side of the pipeline; steps B-D, the allow-list check and the
already-indexed-with-same-hash short-circuit, happen BFF-side against
MariaDB's AI Document Index before this service is ever called).

Architecturally isolated per ARCH Ã‚Â§3.3: no dependency on
orchestrator/agent_registry, no dependency on RagService. Triggered
exclusively by gateway/routers/ingest.py handling a signed POST /ingest
call Ã¢â‚¬â€ never on its own initiative, never on a schedule (UC-8.4's own
non-goal list).
"""
from __future__ import annotations

import asyncpg
import httpx

from app.exceptions import NoExtractableTextError
from app.gateway.schemas.ingest_event import IngestRequest, IngestResult
from app.ingest.workers.embedding_worker import embed_and_store_chunks
from app.observability.logging import get_logger
from app.observability.metrics import INGESTION_FAILED_TOTAL, INGESTION_SUCCEEDED_TOTAL, counters
from app.platform.rag.chunker import chunk_clauses, chunk_pages
from app.platform.rag.embedder import Embedder
from app.platform.vector_store.adapter import VectorStoreAdapter

logger = get_logger(__name__)

# Contract/spec documents are chunked clause-first (more citable spans);
# everything else falls back to page-bounded chunking.
_CLAUSE_CHUNKED_DOCTYPES = {"Commitment"}


def _guess_content_type(file_name: str) -> str:
    lower = file_name.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "text/plain"


class IngestionService:
    def __init__(
        self, vector_store: VectorStoreAdapter, embedder: Embedder, conn: asyncpg.Connection,
    ) -> None:
        self._vector_store = vector_store
        self._embedder = embedder
        self._conn = conn

    async def ingest(self, request: IngestRequest) -> IngestResult:  # noqa: C901
        # Sidecar-side idempotency belt-and-suspenders on top of the BFF's
        # own AI Document Index hash check (Flowchart 5 step D) Ã¢â‚¬â€ a
        # duplicate call for content already indexed here is a no-op, not
        # a re-embed.
        already_indexed = await self._conn.fetchval(
            "SELECT 1 FROM document_chunks WHERE content_hash = $1 AND is_stale = FALSE LIMIT 1",
            request.content_hash,
        )
        if already_indexed:
            logger.info("ingest_noop_already_indexed", content_hash=request.content_hash)
            existing_count = await self._conn.fetchval(
                "SELECT count(*) FROM document_chunks WHERE content_hash = $1", request.content_hash
            )
            return IngestResult(
                status="Indexed", chunk_count=existing_count, model_version=self._embedder.model_version
            )

        try:
            raw_bytes, content_type = await self._obtain_content(request)
            text_or_pages = self._extract_text(raw_bytes, content_type, request.file_name or request.file_id)
        except NoExtractableTextError as exc:
            counters.increment(INGESTION_FAILED_TOTAL)
            logger.warning(
                "ingest_no_extractable_text", file_id=request.file_id, reason=exc.reason
            )
            return IngestResult(status="Failed", failure_reason=exc.reason, status_detail=exc.reason)

        # UC-8.4 A1 Ã¢â‚¬â€ mark any prior chunks for this source stale ahead of
        # re-ingest, never hard-deleting mid-query.
        await self._vector_store.mark_stale(
            request.company, request.source_doctype, request.source_name
        )

        if request.source_doctype in _CLAUSE_CHUNKED_DOCTYPES and isinstance(text_or_pages, str):
            chunks = chunk_clauses(text_or_pages)
        elif isinstance(text_or_pages, list):
            chunks = chunk_pages(text_or_pages)
        else:
            chunks = chunk_pages([text_or_pages])

        chunk_count = await embed_and_store_chunks(
            chunks, request.company, request.project, request.source_doctype,
            request.source_name, request.file_id, request.content_hash,
            self._vector_store, self._embedder,
        )

        counters.increment(INGESTION_SUCCEEDED_TOTAL)
        return IngestResult(
            status="Indexed", chunk_count=chunk_count, model_version=self._embedder.model_version
        )

    async def _obtain_content(self, request: IngestRequest) -> tuple[bytes, str]:
        """Prefers the inline base64 payload BFF actually sends
        (ingestion_trigger_service.py's documented "one fewer moving
        part" design); falls back to a signed-URL fetch for any future
        caller that supplies one instead."""
        if request.content_b64:
            import base64

            raw = base64.b64decode(request.content_b64)
            content_type = _guess_content_type(request.file_name or request.file_id)
            return raw, content_type
        return await self._download(request.signed_download_url)  # type: ignore[arg-type]

    async def _download(self, signed_url: str) -> tuple[bytes, str]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(signed_url)
            response.raise_for_status()
            return response.content, response.headers.get("content-type", "")

    def _extract_text(self, raw_bytes: bytes, content_type: str, file_id: str):
        is_pdf = "pdf" in content_type or file_id.lower().endswith(".pdf")
        is_docx = "wordprocessingml" in content_type or file_id.lower().endswith(".docx")

        if is_pdf:
            return self._extract_pdf(raw_bytes)
        if is_docx:
            return self._extract_docx(raw_bytes)

        # Fall back: treat as plain text if decodable, otherwise fail loud
        # rather than silently indexing binary garbage as "empty content
        # that could later be cited as if it existed" (Flowchart 5's own
        # key rule).
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NoExtractableTextError("unsupported_file_type") from exc

    def _extract_pdf(self, raw_bytes: bytes) -> list[str]:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        pages = [page.get_text().strip() for page in doc]
        doc.close()

        if not any(pages):
            raise NoExtractableTextError("no_text_layer")
        return pages

    def _extract_docx(self, raw_bytes: bytes) -> str:
        import io

        from docx import Document

        doc = Document(io.BytesIO(raw_bytes))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

        if not text.strip():
            raise NoExtractableTextError("no_text_layer")
        return text
