"""Test RAG pipeline (rate-limit aware)."""
import asyncio, sys
sys.path.insert(0, "src")
from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.model_provider import get_model_provider
from buildpolaris_ai.platform.retrieval.connection import create_ai_connection
from buildpolaris_ai.platform.retrieval.rag_service import RagService
from buildpolaris_ai.platform.retrieval.citation_validator import CitationValidator


async def main():
    settings = get_settings()
    print(f"Provider: {settings.model_provider.primary_provider}")
    print(f"Embedding: {settings.embedding.provider}")
    print("---")
    conn = await create_ai_connection()
    provider = get_model_provider()
    validator = CitationValidator(jaccard_threshold=settings.rag.jaccard_threshold)
    service = RagService(
        conn=conn, provider=provider, validator=validator,
        vector_limit=settings.rag.vector_search_limit,
        graph_limit=settings.rag.graph_enrich_limit,
        max_retries=settings.rag.max_generation_retries,
        use_rag_fusion=settings.rag.use_rag_fusion,
        use_query_transform=settings.rag.use_query_transform,
        rerank_top_k=settings.rag.rerank_top_k,
    )
    questions = [
        "What is the status of RFI-1000?",
        "Which tasks are on the critical path?",
        "What punch items are still open?",
    ]
    for i, q in enumerate(questions):
        print(f"\nQ: {q}")
        result = await service.answer(q, "TENANT-ALPHA")
        print(f"A: {result.answer[:200]}")
        print(f"Citations: {len(result.citations)} | Validated: {result.citations_validated}")
        print("-" * 60)
        if i < len(questions) - 1:
            print("...waiting 8s to respect rate limits...")
            await asyncio.sleep(8)
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
