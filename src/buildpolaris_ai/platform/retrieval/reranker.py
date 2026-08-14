"""Cross-encoder re-ranker for retrieved chunks."""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


class CrossEncoderReranker:
    """Re-ranks retrieved chunks using cross-encoder scoring.
    
    Falls back to simple keyword overlap scoring if no model available.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self._model = None
        self._model_name = model_name
        self._initialized = False

    def _ensure_model(self) -> None:
        if self._initialized:
            return
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self._model_name)
            self._initialized = True
            logger.info("CrossEncoder loaded", model=self._model_name)
        except Exception as e:
            logger.warning("CrossEncoder unavailable, using fallback scoring", error=str(e))
            self._initialized = True

    def rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Re-rank documents by relevance to query."""
        self._ensure_model()

        if not documents:
            return []

        if self._model is not None:
            return self._rerank_with_model(query, documents, top_k)
        else:
            return self._rerank_fallback(query, documents, top_k)

    def _rerank_with_model(
        self, query: str, documents: list[dict], top_k: int
    ) -> list[dict]:
        pairs = []
        for doc in documents:
            content = doc.get("content", doc.get("text", ""))
            pairs.append([query, content])

        try:
            scores = self._model.predict(pairs)
            scored_docs = list(zip(documents, scores))
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            return [doc for doc, _ in scored_docs[:top_k]]
        except Exception as e:
            logger.warning("Model reranking failed, using fallback", error=str(e))
            return self._rerank_fallback(query, documents, top_k)

    def _rerank_fallback(
        self, query: str, documents: list[dict], top_k: int
    ) -> list[dict]:
        """Simple keyword overlap scoring as fallback."""
        query_terms = set(query.lower().split())

        scored = []
        for doc in documents:
            content = doc.get("content", doc.get("text", "")).lower()
            content_terms = set(content.split())
            overlap = len(query_terms & content_terms) / max(len(query_terms), 1)
            scored.append((doc, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scored[:top_k]]
