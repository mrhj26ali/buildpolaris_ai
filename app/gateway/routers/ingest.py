"""POST /ingest â€” UC-8.4 steps 5-9. Only ever called by a BFF background
job after its own allow-list + already-indexed check (Flowchart 5 steps
B-D happen BFF-side against MariaDB's AI Document Index).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db.postgres import get_pool
from app.exceptions import ScopeMismatchError
from app.gateway.auth.scope_assertion import ScopeAssertion, verify_scope_assertion
from app.gateway.auth.service_credential import verify_service_credential
from app.gateway.schemas.ingest_event import IngestRequest, IngestResult
from app.ingest.ingestion_service import IngestionService
from app.observability.logging import get_logger
from app.platform.model_provider.factory import get_model_provider
from app.platform.rag.embedder import Embedder
from app.platform.vector_store.pgvector_adapter import PgVectorAdapter

logger = get_logger(__name__)

router = APIRouter(
    prefix="/ingest", tags=["ingest"], dependencies=[Depends(verify_service_credential)]
)


@router.post("", response_model=IngestResult)
async def ingest_document(
    body: IngestRequest,
    assertion: ScopeAssertion = Depends(verify_scope_assertion),
) -> IngestResult:
    # UC-8.4 E3 â€” the ingestion write path gets the same scope-mismatch
    # defense as every read path (NFR-SEC.8), not an exemption because
    # it's a "trusted" BFF-originated call.
    if body.company != assertion.company:
        raise ScopeMismatchError("ingest request company does not match asserted scope")

    async with get_pool().acquire() as conn:
        service = IngestionService(PgVectorAdapter(conn), Embedder(get_model_provider()), conn)
        result = await service.ingest(body)

    logger.info(
        "ingest_completed", source_doctype=body.source_doctype, source_name=body.source_name,
        status=result.status, chunk_count=result.chunk_count,
    )
    return result
