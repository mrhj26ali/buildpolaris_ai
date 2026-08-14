"""Wraps a ModelProviderAdapter call so every completion/embedding call
reports its token usage to the NFR-AIGOV.1 tracker, in one place, rather
than every agent remembering to do it themselves.
"""
from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel

from app.observability.token_usage import get_token_usage_tracker
from app.platform.model_provider.adapter import ModelProviderAdapter, ModelResponse

T = TypeVar("T", bound=BaseModel)


class MeteredModelProvider:
    """Decorates any ModelProviderAdapter with usage metering. Agents and
    RagService depend on ModelProviderAdapter's interface as usual; this
    wrapper is applied once, at provider-resolution time (see factory
    wiring in app/dependencies.py), so metering is never optional or
    forgotten per call site.
    """

    def __init__(self, inner: ModelProviderAdapter, company: str) -> None:
        self._inner = inner
        self._company = company

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    @property
    def default_model_version(self) -> str:
        return self._inner.default_model_version

    async def complete(self, prompt: str, model_version: str | None = None,
                        temperature: float = 0.2, max_tokens: int = 2048) -> ModelResponse:
        response = await self._inner.complete(prompt, model_version, temperature, max_tokens)
        self._record(response)
        return response

    async def structured_complete(self, prompt: str, response_model: Type[T],
                                   model_version: str | None = None,
                                   temperature: float = 0.1) -> T:
        result = await self._inner.structured_complete(
            prompt, response_model, model_version, temperature
        )
        # Structured calls don't always surface token counts from every
        # SDK; estimate conservatively from prompt length when absent so
        # spend is never silently under-tracked.
        estimate = max(len(prompt) // 4, 1)
        get_token_usage_tracker().record_usage(self._company, estimate, estimate // 2)
        return result

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        return await self._inner.embed(text, model_version)

    async def embed_batch(self, texts: list[str], model_version: str | None = None) -> list[list[float]]:
        return await self._inner.embed_batch(texts, model_version)

    def _record(self, response: ModelResponse) -> None:
        get_token_usage_tracker().record_usage(
            self._company, response.prompt_tokens, response.completion_tokens
        )
