"""Embedding service with multiple backend support."""
from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Optional

import structlog

logger = structlog.get_logger()


class EmbeddingService:
    """Generates embeddings using configured provider."""

    def __init__(self) -> None:
        from buildpolaris_ai.platform.config import get_settings
        self._settings = get_settings().embedding
        self._model = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        if self._settings.provider == "sentence-transformers":
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._settings.model)
            logger.info("SentenceTransformer loaded", model=self._settings.model)
        elif self._settings.provider == "ollama":
            logger.info("Using Ollama for embeddings", model=self._settings.ollama_model)

        self._initialized = True

    async def embed_text(self, text: str) -> list[float]:
        await self._ensure_initialized()

        if self._settings.provider == "sentence-transformers":
            import numpy as np
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None, self._model.encode, text
            )
            return embedding.tolist()

        elif self._settings.provider == "ollama":
            import ollama
            client = ollama.AsyncClient()
            response = await client.embeddings(
                model=self._settings.ollama_model, prompt=text
            )
            return response["embedding"]

        raise ValueError(f"Unknown embedding provider: {self._settings.provider}")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        await self._ensure_initialized()
        results = []
        batch_size = self._settings.batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            if self._settings.provider == "sentence-transformers":
                import numpy as np
                loop = asyncio.get_event_loop()
                embeddings = await loop.run_in_executor(
                    None, self._model.encode, batch
                )
                results.extend([e.tolist() for e in embeddings])
            else:
                for text in batch:
                    results.append(await self.embed_text(text))

        return results

    @property
    def dimensions(self) -> int:
        return self._settings.dimensions


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
