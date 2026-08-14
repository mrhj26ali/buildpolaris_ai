"""Resolves the configured primary + fallback ModelProviderAdapter pair
and wraps every call through the circuit breaker, so `RagService` and
every agent depend only on `ResilientModelProvider` â€” a single object
that behaves like a `ModelProviderAdapter` but internally fails over.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Type, TypeVar

from pydantic import BaseModel

from app.config import Settings, get_settings
from app.exceptions import ModelProviderUnavailableError
from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelProviderAdapter, ModelResponse
from app.platform.model_provider.circuit_breaker import get_circuit_breaker

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


def _build_provider(name: str, settings: Settings) -> ModelProviderAdapter | None:
    mp = settings.model_provider
    if name == "gemini":
        if not mp.gemini_api_key:
            return None
        from app.platform.model_provider.gemini_adapter import GeminiProvider

        return GeminiProvider(
            api_key=mp.gemini_api_key.get_secret_value(),
            model=mp.gemini_model,
            embedding_model=mp.gemini_embedding_model,
        )
    if name == "ollama":
        from app.platform.model_provider.ollama_adapter import OllamaProvider

        return OllamaProvider(base_url=mp.ollama_base_url, model=mp.ollama_model)
    if name == "anthropic":
        if not mp.anthropic_api_key:
            return None
        from app.platform.model_provider.anthropic_adapter import AnthropicProvider

        return AnthropicProvider(api_key=mp.anthropic_api_key.get_secret_value(), model=mp.anthropic_model)
    if name == "openai":
        if not mp.openai_api_key:
            return None
        from app.platform.model_provider.openai_adapter import OpenAIProvider

        return OpenAIProvider(api_key=mp.openai_api_key.get_secret_value(), model=mp.openai_model)
    if name == "none":
        return None
    raise ValueError(f"unknown model provider '{name}'")


class ResilientModelProvider:
    """Implements ModelProviderAdapter's shape while internally trying the
    primary provider first, and the configured fallback if the primary's
    breaker is open or the call itself fails."""

    def __init__(self, primary: ModelProviderAdapter, fallback: ModelProviderAdapter | None) -> None:
        self._primary = primary
        self._fallback = fallback
        self._breaker = get_circuit_breaker()

    @property
    def provider_name(self) -> str:
        return self._primary.provider_name

    @property
    def default_model_version(self) -> str:
        return self._primary.default_model_version

    async def _with_fallback(self, method_name: str, *args, **kwargs):
        try:
            fn = getattr(self._primary, method_name)
            return await self._breaker.call_with_breaker(
                self._primary.provider_name, lambda: fn(*args, **kwargs)
            )
        except Exception as primary_exc:
            if self._fallback is None:
                raise
            logger.warning(
                "model_provider_falling_back",
                primary=self._primary.provider_name,
                fallback=self._fallback.provider_name,
                error=str(primary_exc),
            )
            try:
                fn = getattr(self._fallback, method_name)
                return await self._breaker.call_with_breaker(
                    self._fallback.provider_name, lambda: fn(*args, **kwargs)
                )
            except Exception as fallback_exc:
                raise ModelProviderUnavailableError(
                    f"primary '{self._primary.provider_name}' and fallback "
                    f"'{self._fallback.provider_name}' both failed"
                ) from fallback_exc

    async def complete(self, prompt: str, model_version: str | None = None,
                        temperature: float = 0.2, max_tokens: int = 2048) -> ModelResponse:
        return await self._with_fallback("complete", prompt, model_version, temperature, max_tokens)

    async def structured_complete(self, prompt: str, response_model: Type[T],
                                   model_version: str | None = None, temperature: float = 0.1) -> T:
        return await self._with_fallback(
            "structured_complete", prompt, response_model, model_version, temperature
        )

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        return await self._with_fallback("embed", text, model_version)

    async def embed_batch(self, texts: list[str], model_version: str | None = None) -> list[list[float]]:
        return await self._with_fallback("embed_batch", texts, model_version)


@lru_cache
def get_model_provider() -> ResilientModelProvider:
    settings = get_settings()
    mp = settings.model_provider

    primary = _build_provider(mp.primary, settings)
    if primary is None:
        raise ModelProviderUnavailableError(
            f"primary provider '{mp.primary}' is not configured (missing API key?)"
        )
    fallback = _build_provider(mp.fallback, settings)

    logger.info(
        "model_provider_resolved",
        primary=mp.primary,
        fallback=mp.fallback if fallback else "none",
    )
    return ResilientModelProvider(primary, fallback)
