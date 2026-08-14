"""RagService â€” the pipeline behind a 'grounded factual question' turn
(ARCH Flowchart 4, steps F through L). This is the one place that wires
query_transform -> retriever (vector + graph) -> rrf -> reranker ->
generation -> citation_validator -> retry-once-or-refuse together; every
other module in platform/rag is a stage this file calls in order.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import get_settings
from app.observability.logging import get_logger
from app.observability.metrics import (
    CITATION_VALIDATION_FAILURES_TOTAL,
    CITATION_VALIDATION_REFUSALS_TOTAL,
    counters,
)
from app.platform.citations.citation_formatter import format_answer_with_citations
from app.platform.citations.citation_validator import CitationValidator, ValidatedCitation
from app.platform.graph_store.adapter import GraphStoreAdapter
from app.platform.model_provider.adapter import ModelProviderAdapter
from app.platform.rag.query_transform import transform_query
from app.platform.rag.reranker import rerank
from app.platform.rag.retriever import Retriever
from app.platform.rag.rrf import reciprocal_rank_fusion
from app.platform.vector_store.adapter import ScoredChunk, VectorStoreAdapter

logger = get_logger(__name__)

ANSWER_PROMPT = """You are the BuildPolaris AI Copilot, answering a
question about this construction project using ONLY the context passages
below. Every factual claim in your answer MUST be immediately followed by
a citation marker like [1], [2] referencing the passage it came from. If
the context does not contain the answer, say so plainly â€” never invent a
citation or state something the context doesn't support.

Context passages:
{context}

Question: {question}

Answer (with [n] citation markers after every claim):
"""

STRICTER_RETRY_SUFFIX = """

IMPORTANT: Your previous answer contained a claim that could not be
matched back to a real passage above. This time, cite ONLY passages that
are copied from the context below, and if you are not certain a claim is
directly supported, omit that claim entirely rather than guessing.
"""


@dataclass(slots=True)
class RagAnswer:
    text: str
    citations: list[ValidatedCitation] = field(default_factory=list)
    refused: bool = False
    model_version: str = ""


class RagService:
    def __init__(
        self,
        vector_store: VectorStoreAdapter,
        graph_store: GraphStoreAdapter,
        model_provider: ModelProviderAdapter,
        retriever: Retriever,
        citation_validator: CitationValidator,
    ) -> None:
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._model_provider = model_provider
        self._retriever = retriever
        self._citation_validator = citation_validator

    async def answer(self, question: str, company: str, project: str | None) -> RagAnswer:
        settings = get_settings().rag

        # F: query transformation (2-4 reformulations)
        queries = await transform_query(question, self._model_provider, settings.query_reformulations)

        # G: hybrid retrieval â€” vector search (parallel per reformulation) + graph traversal
        ranked_lists = await self._retriever.vector_search_many(
            queries, company, project, settings.vector_search_limit
        )
        top_vector_hits = ranked_lists[0] if ranked_lists else []
        graph_hits = await self._retriever.graph_enrich(
            top_vector_hits, company, settings.graph_traversal_limit
        )

        # H: Reciprocal Rank Fusion -> deduplicated context
        fused: list[ScoredChunk] = reciprocal_rank_fusion(
            ranked_lists, key_fn=lambda c: c.chunk_id
        )
        fused = await rerank(question, fused, settings.rerank_top_k)

        if not fused:
            logger.info("rag_no_context_found", company=company, project=project)
            return RagAnswer(
                text="I couldn't find anything in the indexed documents that answers this.",
                refused=False,
                model_version=self._model_provider.default_model_version,
            )

        # I: draft answer with per-claim citations
        answer_text, validated = await self._generate_and_validate(question, fused)

        if answer_text is None:
            counters.increment(CITATION_VALIDATION_REFUSALS_TOTAL)
            return RagAnswer(
                text="I found related content but couldn't verify a claim against "
                     "the source documents closely enough to answer confidently. "
                     "Please check the underlying documents directly.",
                refused=True,
                model_version=self._model_provider.default_model_version,
            )

        return RagAnswer(
            text=answer_text,
            citations=validated,
            refused=False,
            model_version=self._model_provider.default_model_version,
        )

    async def _generate_and_validate(
        self, question: str, chunks: list[ScoredChunk]
    ) -> tuple[str | None, list[ValidatedCitation]]:
        settings = get_settings().rag
        context = format_answer_with_citations(chunks)

        prompt = ANSWER_PROMPT.format(context=context, question=question)
        attempt = 0
        while True:
            response = await self._model_provider.complete(prompt, temperature=0.1)
            valid, validated = self._citation_validator.validate(response.text, chunks)

            if valid:
                return response.text, validated

            counters.increment(CITATION_VALIDATION_FAILURES_TOTAL)
            attempt += 1
            if attempt > settings.max_citation_retries:
                logger.warning("citation_validation_exhausted_refusing", question=question)
                return None, []

            logger.info("citation_validation_retry", attempt=attempt)
            prompt = ANSWER_PROMPT.format(context=context, question=question) + STRICTER_RETRY_SUFFIX
