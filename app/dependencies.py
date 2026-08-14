"""FastAPI dependency wiring â€” the composition root. Every router pulls
its collaborators from here rather than constructing adapters inline, so
swapping an adapter (NFR-EXT.2) touches exactly this file.
"""
from __future__ import annotations

from functools import lru_cache
from typing import AsyncIterator

import asyncpg
from fastapi import Depends

from app.db.session import get_db_conn
from app.gateway.auth.scope_assertion import ScopeAssertion, verify_scope_assertion
from app.orchestrator.agent_registry import AgentRegistry, get_agent_registry
from app.orchestrator.turn_runner import TurnRunner
from app.platform.citations.citation_validator import CitationValidator
from app.platform.graph_store.age_adapter import AgeGraphAdapter
from app.platform.model_provider.factory import get_model_provider
from app.platform.rag.embedder import Embedder
from app.platform.rag.rag_service import RagService
from app.platform.rag.retriever import Retriever
from app.platform.vector_store.pgvector_adapter import PgVectorAdapter


@lru_cache
def get_citation_validator() -> CitationValidator:
    return CitationValidator()


def get_embedder() -> Embedder:
    return Embedder(get_model_provider())


async def get_vector_store(conn: asyncpg.Connection = Depends(get_db_conn)) -> PgVectorAdapter:
    return PgVectorAdapter(conn)


async def get_graph_store(conn: asyncpg.Connection = Depends(get_db_conn)) -> AgeGraphAdapter:
    return AgeGraphAdapter(conn)


async def get_retriever(
    vector_store: PgVectorAdapter = Depends(get_vector_store),
    graph_store: AgeGraphAdapter = Depends(get_graph_store),
) -> Retriever:
    return Retriever(vector_store, graph_store, get_embedder())


async def get_rag_service_dep(
    vector_store: PgVectorAdapter = Depends(get_vector_store),
    graph_store: AgeGraphAdapter = Depends(get_graph_store),
    retriever: Retriever = Depends(get_retriever),
) -> RagService:
    return RagService(
        vector_store=vector_store, graph_store=graph_store, model_provider=get_model_provider(),
        retriever=retriever, citation_validator=get_citation_validator(),
    )


# Non-DI accessor for callers outside a request lifecycle (agents calling
# back into RagService need a plain awaitable-returning function, not a
# FastAPI Depends chain â€” see app/agents/submittal_review/handler.py and
# app/agents/contract_clause_extraction/handler.py). Always called from
# inside an already-running event loop (an agent's own `run()`), so this
# defers connection acquisition to the `.answer()` call itself rather
# than holding a pooled connection open for the agent's entire run.
class _LazyRagService:
    async def answer(self, question: str, company: str, project: str | None):
        from app.db.postgres import get_pool

        async with get_pool().acquire() as conn:
            vector_store = PgVectorAdapter(conn)
            graph_store = AgeGraphAdapter(conn)
            retriever = Retriever(vector_store, graph_store, get_embedder())
            service = RagService(
                vector_store=vector_store, graph_store=graph_store,
                model_provider=get_model_provider(), retriever=retriever,
                citation_validator=get_citation_validator(),
            )
            return await service.answer(question, company, project)


def get_rag_service() -> "_LazyRagService":
    return _LazyRagService()


async def get_turn_runner(
    rag_service: RagService = Depends(get_rag_service_dep),
    registry: AgentRegistry = Depends(get_agent_registry),
) -> TurnRunner:
    return TurnRunner(registry, rag_service)


async def get_ingestion_service(conn: asyncpg.Connection = Depends(get_db_conn)):
    from app.ingest.ingestion_service import IngestionService

    return IngestionService(PgVectorAdapter(conn), get_embedder(), conn)


async def get_entity_mirror_service(conn: asyncpg.Connection = Depends(get_db_conn)):
    from app.ingest.entity_mirror_service import EntityMirrorService

    return EntityMirrorService(AgeGraphAdapter(conn), conn)


def require_scope(assertion: ScopeAssertion = Depends(verify_scope_assertion)) -> ScopeAssertion:
    return assertion
