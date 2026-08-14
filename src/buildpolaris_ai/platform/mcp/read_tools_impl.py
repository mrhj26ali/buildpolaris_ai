"""Implementation functions for read-only MCP tools.

This module deliberately has no MCP transport dependency.
It can be imported safely by the orchestrator, tests, and workers.

Read-only tools:
- search_knowledge_impl
- enrich_context_impl
- answer_question_impl

Write tools are deliberately NOT here; they must go through governance.
"""

from __future__ import annotations

from typing import Any

import structlog

from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.model_provider import get_model_provider
from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter
from buildpolaris_ai.platform.retrieval.citation_validator import CitationValidator
from buildpolaris_ai.platform.retrieval.connection import ai_connection
from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
from buildpolaris_ai.platform.retrieval.rag_service import RagService

logger = structlog.get_logger()


async def _embed(text: str) -> list[float]:
    """Embed text using the local embedding model.

    Phase A keeps embeddings local via Ollama/nomic-embed-text.
    Generation can use Gemini/OpenAI-compatible providers while embeddings stay local.
    """
    import ollama

    client = ollama.AsyncClient()
    response = await client.embeddings(model="nomic-embed-text", prompt=text)
    return response["embedding"]


async def search_knowledge_impl(
    question: str,
    tenant_id: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Semantic search over tenant-scoped embeddings."""
    async with ai_connection() as conn:
        vector_store = PgVectorAdapter(conn)
        embedding = await _embed(question)
        return await vector_store.search(embedding, tenant_id, limit=limit)


async def enrich_context_impl(
    docnames: list[str],
    tenant_id: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Graph enrichment from seed docnames."""
    if not docnames:
        return []

    async with ai_connection() as conn:
        graph_store = AGEAdapter(conn)
        return await graph_store.enrich_with_graph_context(
            docnames,
            tenant_id,
            limit=limit,
        )


async def answer_question_impl(
    question: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Full hybrid RAG answer with validated citations."""
    settings = get_settings()

    async with ai_connection() as conn:
        provider = get_model_provider()
        validator = CitationValidator(
            jaccard_threshold=settings.rag.jaccard_threshold
        )
        service = RagService(
            conn=conn,
            provider=provider,
            validator=validator,
            vector_limit=settings.rag.vector_search_limit,
            graph_limit=settings.rag.graph_enrich_limit,
            max_retries=settings.rag.max_generation_retries,
        )

        result = await service.answer(question, tenant_id)

        return {
            "answer": result.answer,
            "citations": result.citations,
            "citations_validated": result.citations_validated,
            "attempts": result.attempts,
        }
