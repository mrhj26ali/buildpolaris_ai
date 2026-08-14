"""Production hybrid RAG endpoint (FR-8.3). Tenant-scoped, citation-validated."""

from typing import Optional

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.model_provider import get_model_provider
from buildpolaris_ai.platform.retrieval.citation_validator import CitationValidator
from buildpolaris_ai.platform.retrieval.connection import get_ai_db_conn
from buildpolaris_ai.platform.retrieval.rag_service import RagService

logger = structlog.get_logger()

router = APIRouter(prefix="/rag", tags=["RAG"])


class RagQueryRequest(BaseModel):
    question: str
    tenant_id: Optional[str] = None


@router.post("/query")
async def rag_query(
    req: RagQueryRequest,
    conn: asyncpg.Connection = Depends(get_ai_db_conn),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
):
    settings = get_settings()
    tenant_id = req.tenant_id or x_tenant_id or "TENANT-ALPHA"

    provider = get_model_provider()
    validator = CitationValidator(jaccard_threshold=settings.rag.jaccard_threshold)

    service = RagService(
        conn=conn,
        provider=provider,
        validator=validator,
        vector_limit=settings.rag.vector_search_limit,
        graph_limit=settings.rag.graph_enrich_limit,
        max_retries=settings.rag.max_generation_retries,
    )

    result = await service.answer(req.question, tenant_id)

    return {
        "answer": result.answer,
        "citations": result.citations,
        "citations_validated": result.citations_validated,
        "attempts": result.attempts,
        "tenant_id": tenant_id,
    }
