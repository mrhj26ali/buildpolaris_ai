"""Advanced Hybrid RAG: embed -> multi-query -> vector search -> graph enrichment
-> RAG Fusion -> re-rank -> schema-forced generation -> citation validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter
from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
from buildpolaris_ai.platform.retrieval.citation_validator import CitationValidator, RAGResponse
from buildpolaris_ai.platform.retrieval.query_transformer import QueryTransformer
from buildpolaris_ai.platform.retrieval.rag_fusion import ReciprocalRankFusion
from buildpolaris_ai.platform.retrieval.reranker import CrossEncoderReranker
from buildpolaris_ai.platform.model_provider.protocol import ModelProviderProtocol

logger = structlog.get_logger()

NO_INFO_ANSWER = "I don't have enough information in the knowledge base to answer that."

BASE_PROMPT = """You are a construction project management assistant.
Answer the user's question based ONLY on the provided context.
Output valid JSON with "answer" and "citations" fields.

RULES:
1. If you find the answer, provide at least one citation.
2. Each citation's "source_docname" must match a document in the context.
3. Each citation's "quoted_span" must be an EXACT verbatim substring from the context.
4. If the answer is NOT in the context, set "answer" to "{no_info}" and "citations" to [].

Context:
{context}

Question: {question}
"""

STRICT_PROMPT = """You are a careful construction project management assistant.
Answer ONLY if explicitly stated in the context. Do NOT infer or guess.
Output valid JSON with "answer" and "citations" fields.

STRICT RULES:
1. Copy quoted text VERBATIM, character for character, from context.
2. If not literally present, set "answer" to "{no_info}" and "citations" to [].

Context:
{context}

Question: {question}
"""


@dataclass
class RetrievalResult:
    vector_results: list[dict[str, Any]] = field(default_factory=list)
    graph_results: list[dict[str, Any]] = field(default_factory=list)
    fused_results: list[Any] = field(default_factory=list)
    reranked_results: list[dict[str, Any]] = field(default_factory=list)
    context: str = ""
    source_documents: dict[str, str] = field(default_factory=dict)


@dataclass
class RagAnswer:
    answer: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    citations_validated: bool = False
    attempts: int = 0
    retrieval: Optional[RetrievalResult] = None


class RagService:
    """Full RAG pipeline with RAG Fusion, HyDE, graph enrichment, and re-ranking."""

    def __init__(
        self,
        conn,
        provider: ModelProviderProtocol,
        validator: Optional[CitationValidator] = None,
        embed_fn=None,
        vector_limit: int = 10,
        graph_limit: int = 5,
        max_retries: int = 2,
        use_rag_fusion: bool = True,
        use_query_transform: bool = True,
        rerank_top_k: int = 5,
    ) -> None:
        self.conn = conn
        self.provider = provider
        self.validator = validator or CitationValidator()
        self.vector_store = PgVectorAdapter(conn)
        self.graph_store = AGEAdapter(conn)
        self._embed_fn = embed_fn
        self.vector_limit = vector_limit
        self.graph_limit = graph_limit
        self.max_retries = max_retries
        self.use_rag_fusion = use_rag_fusion
        self.use_query_transform = use_query_transform
        self.rerank_top_k = rerank_top_k

        # Advanced retrieval components
        self.query_transformer = QueryTransformer(provider)
        self.rag_fusion = ReciprocalRankFusion(k=60)
        self.reranker = CrossEncoderReranker()

    async def _embed(self, text: str) -> list[float]:
        if self._embed_fn is not None:
            return await self._embed_fn(text)
        from buildpolaris_ai.platform.embedding import get_embedding_service
        service = get_embedding_service()
        return await service.embed_text(text)

    async def retrieve(self, question: str, tenant_id: str) -> RetrievalResult:
        """Full retrieval pipeline with RAG Fusion."""
        result = RetrievalResult()

        # Step 1: Query transformation
        queries = [question]
        if self.use_query_transform:
            try:
                variants = await self.query_transformer.generate_query_variants(question, 3)
                queries = list(set(queries + variants))
                logger.info("Query variants generated", count=len(queries))
            except Exception as e:
                logger.warning("Query transform failed", error=str(e))

        # Step 2: HyDE (Hypothetical Document Embeddings)
        if self.use_query_transform:
            try:
                hyde_doc = await self.query_transformer.generate_hyde(question)
                queries.append(hyde_doc)
            except Exception:
                pass

        # Step 3: Multi-query vector retrieval
        all_result_sets = []
        for query in queries[:5]:  # Cap at 5 queries
            try:
                embedding = await self._embed(query)
                results = await self.vector_store.search(embedding, tenant_id, limit=self.vector_limit)
                # Tag results with source query
                for r in results:
                    r["_query"] = query
                    if "metadata" in r and isinstance(r["metadata"], dict):
                        r["content"] = r["metadata"].get("description", "")
                        r["docname"] = r["metadata"].get("docname", "")
                all_result_sets.append(results)
            except Exception as e:
                logger.warning("Vector search failed for query", query=query[:50], error=str(e))

        # Step 4: RAG Fusion (Reciprocal Rank Fusion)
        if len(all_result_sets) > 1 and self.use_rag_fusion:
            fused = self.rag_fusion.fuse(all_result_sets, top_k=self.vector_limit)
            result.fused_results = fused
            result.vector_results = [
                {"docname": f.docname, "content": f.content, "metadata": f.metadata, "score": f.fused_score}
                for f in fused
            ]
        elif all_result_sets:
            result.vector_results = all_result_sets[0]

        if not result.vector_results:
            return result

        # Step 5: Graph enrichment
        seed_docnames = [
            r.get("docname") or r.get("metadata", {}).get("docname")
            for r in result.vector_results
            if r.get("docname") or r.get("metadata", {}).get("docname")
        ]

        if seed_docnames:
            try:
                result.graph_results = await self.graph_store.enrich_with_graph_context(
                    seed_docnames[:5], tenant_id, limit=self.graph_limit
                )
            except Exception as e:
                logger.warning("Graph enrichment failed", error=str(e))

        # Step 6: Build context
        result.context, result.source_documents = self._build_context(
            result.vector_results, result.graph_results
        )

        # Step 7: Re-rank
        if result.vector_results:
            docs_for_rerank = [
                {"content": r.get("content", ""), "docname": r.get("docname", "")}
                for r in result.vector_results
            ]
            result.reranked_results = self.reranker.rerank(
                question, docs_for_rerank, top_k=self.rerank_top_k
            )

        return result

    @staticmethod
    def _build_context(vector_results, graph_results):
        context = ""
        sources: dict[str, str] = {}

        for res in vector_results:
            meta = res.get("metadata", {})
            docname = res.get("docname") or meta.get("docname", "Unknown")
            doctype = meta.get("doctype", "Unknown")
            subject = meta.get("subject") or meta.get("title") or ""
            description = meta.get("description", "")
            status = meta.get("status", "N/A")
            body = f"Type: {doctype} Subject: {subject} Status: {status} Description: {description}"
            context += f"[Document: {docname}]\n{body}\n\n"
            sources[docname] = body

        for res in graph_results:
            docname = res.get("docname")
            if not docname or docname in sources:
                continue
            body = (
                f"Type: {res.get('doctype')} "
                f"Relationship: {res.get('relationship')} "
                f"Subject: {res.get('subject')}"
            )
            context += f"[Related Document: {docname}]\n{body}\n\n"
            sources[docname] = body

        return context, sources

    async def answer(self, question: str, tenant_id: str) -> RagAnswer:
        """Full RAG answer pipeline with citation validation."""
        retrieval = await self.retrieve(question, tenant_id)

        if not retrieval.source_documents:
            return RagAnswer(
                answer=NO_INFO_ANSWER, citations=[], citations_validated=True,
                attempts=0, retrieval=retrieval,
            )

        attempts = 0
        last_response: Optional[RAGResponse] = None
        prompts = [BASE_PROMPT] + [STRICT_PROMPT] * self.max_retries

        for prompt_template in prompts:
            attempts += 1
            prompt = prompt_template.format(
                no_info=NO_INFO_ANSWER, context=retrieval.context, question=question
            )

            try:
                response = await self.provider.structured_generate(prompt, RAGResponse)
            except Exception as e:
                logger.error("LLM generation failed", attempt=attempts, error=str(e))
                continue

            last_response = response

            if self.validator.validate(response, retrieval.source_documents):
                return RagAnswer(
                    answer=response.answer,
                    citations=[c.model_dump() for c in response.citations],
                    citations_validated=True,
                    attempts=attempts,
                    retrieval=retrieval,
                )

            logger.warning("Citation validation failed, retrying stricter", attempt=attempts)

        logger.warning("All citation validation attempts failed", attempts=attempts)
        return RagAnswer(
            answer="I couldn't verify the sources for this answer. Please check the documents manually.",
            citations=[], citations_validated=False, attempts=attempts, retrieval=retrieval,
        )
