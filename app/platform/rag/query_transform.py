"""Query transformation â€” 2-4 reformulations (ARCH Â§3.3 point 2 / Flowchart
4 step F: "Query transformation (2-4 reformulations)").

A single user question is often a poor literal match for how a contract
clause or RFI response is actually phrased. Reformulating into several
paraphrases before retrieval measurably improves recall for this kind of
domain-specific corpus (construction contract language, field jargon)
without needing a fine-tuned retriever.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelProviderAdapter

logger = get_logger(__name__)


class _Reformulations(BaseModel):
    queries: list[str] = Field(..., min_length=1, max_length=4)


REFORMULATION_PROMPT = """You are helping search a construction project's
documents (contracts, RFIs, submittals, daily logs). Given the user's
question, produce {n} distinct search-engine-style reformulations that
would each independently retrieve relevant passages. Vary vocabulary
(formal contract language vs. field jargon) and specificity. Do not answer
the question â€” only produce search queries.

Question: {question}
"""


async def transform_query(
    question: str, provider: ModelProviderAdapter, n: int = 3
) -> list[str]:
    n = max(2, min(n, 4))
    prompt = REFORMULATION_PROMPT.format(n=n, question=question)
    try:
        result = await provider.structured_complete(prompt, _Reformulations, temperature=0.3)
        queries = [q.strip() for q in result.queries if q.strip()]
    except Exception as exc:  # noqa: BLE001 â€” transform is best-effort
        logger.warning("query_transform_failed_using_original", error=str(exc))
        queries = []

    if question not in queries:
        queries.insert(0, question)
    return queries[: n + 1]
