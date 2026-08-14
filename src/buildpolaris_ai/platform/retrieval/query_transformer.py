"""Query transformation: multi-query generation, HyDE, step-back prompting."""
from __future__ import annotations

from typing import Optional

import structlog
from pydantic import BaseModel, Field

from buildpolaris_ai.platform.model_provider.protocol import ModelProviderProtocol

logger = structlog.get_logger()


class QueryVariants(BaseModel):
    """Multiple reformulated queries for RAG Fusion."""
    queries: list[str] = Field(default_factory=list)


class HypotheticalDocument(BaseModel):
    """HyDE: hypothetical answer document."""
    content: str


class QueryTransformer:
    """Transforms user queries for better retrieval."""

    def __init__(self, provider: ModelProviderProtocol) -> None:
        self.provider = provider

    async def generate_query_variants(
        self, question: str, num_variants: int = 3
    ) -> list[str]:
        """RAG Fusion: generate multiple query perspectives."""
        prompt = f"""You are a construction project management expert.
Given the following question, generate {num_variants} alternative search queries
that would help find relevant information in a construction project database.
Each query should approach the question from a different angle.

Original question: "{question}"

Return exactly {num_variants} queries as a JSON list."""

        try:
            result = await self.provider.structured_generate(prompt, QueryVariants)
            variants = [q for q in result.queries if q.strip()][:num_variants]
            # Always include original
            if question not in variants:
                variants.insert(0, question)
            return variants
        except Exception as e:
            logger.warning("Query variant generation failed, using original", error=str(e))
            return [question]

    async def generate_hyde(self, question: str) -> str:
        """HyDE: Generate hypothetical document that would answer the question."""
        prompt = f"""You are a construction project management database.
Write a short passage (2-3 sentences) that would directly answer this question.
Write it as if it were a real document excerpt from a construction project system.
Be specific with realistic construction terminology.

Question: "{question}"

Passage:"""

        try:
            result = await self.provider.structured_generate(prompt, HypotheticalDocument)
            return result.content
        except Exception as e:
            logger.warning("HyDE generation failed", error=str(e))
            return question

    async def step_back_prompt(self, question: str) -> str:
        """Generate a broader, more abstract version of the question."""
        prompt = f"""Given this specific construction question, generate ONE broader,
more general question that would help retrieve relevant background context.

Specific question: "{question}"

Broader question (one sentence only):"""

        try:
            text = await self.provider.generate_text(prompt, max_tokens=100)
            return text.strip() or question
        except Exception:
            return question
