"""RAG Fusion: multi-query retrieval with Reciprocal Rank Fusion (RRF)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class FusedResult:
    docname: str
    content: str
    metadata: dict = field(default_factory=dict)
    fused_score: float = 0.0
    source_queries: list[str] = field(default_factory=list)


class ReciprocalRankFusion:
    """Combines multiple retrieval result sets using RRF.
    
    RRF score = sum(1 / (k + rank_i)) for each query that retrieved the doc.
    k=60 is the standard constant from the RRF paper.
    """

    def __init__(self, k: int = 60) -> None:
        self.k = k

    def fuse(
        self,
        result_sets: list[list[dict[str, Any]]],
        top_k: int = 10,
    ) -> list[FusedResult]:
        """Fuse multiple ranked result lists into one."""
        doc_scores: dict[str, float] = {}
        doc_contents: dict[str, str] = {}
        doc_metadata: dict[str, dict] = {}
        doc_queries: dict[str, list[str]] = {}

        for query_results in result_sets:
            for rank, result in enumerate(query_results, start=1):
                docname = result.get("docname", result.get("id", str(rank)))
                rrf_score = 1.0 / (self.k + rank)

                doc_scores[docname] = doc_scores.get(docname, 0.0) + rrf_score

                # Store content (first occurrence wins)
                content = result.get("content", result.get("text", ""))
                if content and docname not in doc_contents:
                    doc_contents[docname] = content
                    doc_metadata[docname] = result.get("metadata", {})

                # Track which queries found this doc
                query = result.get("_query", "")
                if query and query not in doc_queries.get(docname, []):
                    doc_queries.setdefault(docname, []).append(query)

        # Sort by fused score
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for docname, score in sorted_docs:
            results.append(FusedResult(
                docname=docname,
                content=doc_contents.get(docname, ""),
                metadata=doc_metadata.get(docname, {}),
                fused_score=score,
                source_queries=doc_queries.get(docname, []),
            ))

        return results
