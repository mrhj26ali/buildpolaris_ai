"""Factory: creates model provider with primary + fallback chain."""
from __future__ import annotations

import structlog

from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.model_provider.protocol import ModelProviderProtocol

logger = structlog.get_logger()

_provider_instance: ModelProviderProtocol | None = None


def get_model_provider() -> ModelProviderProtocol:
    """Create model provider from config. Cached singleton."""
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    settings = get_settings()
    mp = settings.model_provider

    # Try primary provider
    provider = _create_provider(mp.primary_provider, mp)
    if provider:
        _provider_instance = provider
        return provider

    # Try fallback
    logger.warning("Primary provider failed, trying fallback", primary=mp.primary_provider)
    if mp.primary_provider != "gemini" and mp.gemini_api_key:
        provider = _create_provider("gemini", mp)
        if provider:
            _provider_instance = provider
            return provider

    # Last resort: Ollama (local, always available)
    logger.warning("All cloud providers failed, falling back to Ollama")
    provider = _create_provider("ollama", mp)
    _provider_instance = provider
    return provider


def _create_provider(provider_type: str, mp) -> ModelProviderProtocol | None:
    try:
        if provider_type == "groq" and mp.groq_api_key:
            from buildpolaris_ai.platform.model_provider.groq_adapter import GroqProvider
            return GroqProvider(
                api_key=mp.groq_api_key.get_secret_value(),
                model=mp.groq_model,
            )
        elif provider_type == "gemini" and mp.gemini_api_key:
            from buildpolaris_ai.platform.model_provider.gemini_adapter import GeminiProvider
            return GeminiProvider(
                api_key=mp.gemini_api_key.get_secret_value(),
                model=mp.gemini_model,
            )
        elif provider_type == "ollama":
            from buildpolaris_ai.platform.model_provider.instructor_adapter import InstructorProvider
            return InstructorProvider(
                provider_id=f"ollama/{mp.ollama_model}",
                base_url=mp.ollama_base_url,
            )
        else:
            logger.warning(f"Provider {provider_type} not configured")
            return None
    except Exception as e:
        logger.error(f"Failed to create provider {provider_type}", error=str(e))
        return None


def reset_provider() -> None:
    """Reset cached provider (for testing)."""
    global _provider_instance
    _provider_instance = None
