# src/buildpolaris_ai/platform/model_provider/factory.py
"""
Factory for creating the model provider from config.

This is the SINGLE SEAM for model provider selection.
Callers use `get_model_provider()` and never instantiate adapters directly.
Changing the provider is a config change (MODEL_PROVIDER__PROVIDER_ID),
not a code change — per Decision Log #6.
"""
from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.model_provider.instructor_adapter import InstructorProvider
from buildpolaris_ai.platform.model_provider.protocol import ModelProviderProtocol


def get_model_provider() -> ModelProviderProtocol:
    """
    Create the model provider from centralized config.

    Returns an adapter satisfying ModelProviderProtocol, configured by:
      - settings.model_provider.provider_id  (e.g., "ollama/qwen2.5:3b-instruct")
      - settings.model_provider.api_key      (for hosted providers like Gemini)
      - settings.model_provider.base_url     (optional, e.g., custom Ollama host)
    """
    settings = get_settings()
    return InstructorProvider(
        provider_id=settings.model_provider.provider_id,
        api_key=settings.model_provider.api_key,
        base_url=settings.model_provider.base_url,
    )