"""Embedder â€” thin wrapper resolving which provider actually performs
embedding (config allows pinning embeddings to a different provider than
completion, since the free-tier Gemini embedding quota and the free-tier
Gemini generation quota are tracked separately upstream).
"""
from __future__ import annotations

from app.config import get_settings
from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelProviderAdapter

logger = get_logger(__name__)


class Embedder:
    def __init__(self, provider: ModelProviderAdapter) -> None:
        self._provider = provider
        self._settings = get_settings().embedding

    async def embed_text(self, text: str) -> list[float]:
        if self._settings.provider == "sentence-transformers":
            return await self._embed_local(text)
        return await self._provider.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self._settings.provider == "sentence-transformers":
            return await self._embed_local_batch(texts)
        return await self._provider.embed_batch(texts)

    # --- local sentence-transformers path (free, no API quota) ---------
    _local_model = None

    async def _ensure_local_model(self):
        if Embedder._local_model is None:
            from sentence_transformers import SentenceTransformer

            Embedder._local_model = SentenceTransformer(self._settings.model)
            logger.info("sentence_transformers_loaded", model=self._settings.model)
        return Embedder._local_model

    async def _embed_local(self, text: str) -> list[float]:
        import asyncio

        model = await self._ensure_local_model()
        loop = asyncio.get_event_loop()
        vec = await loop.run_in_executor(None, model.encode, text)
        return vec.tolist()

    async def _embed_local_batch(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        model = await self._ensure_local_model()
        loop = asyncio.get_event_loop()
        vecs = await loop.run_in_executor(None, model.encode, texts)
        return [v.tolist() for v in vecs]

    @property
    def dimensions(self) -> int:
        return self._settings.dimensions

    @property
    def model_version(self) -> str:
        return self._settings.model
