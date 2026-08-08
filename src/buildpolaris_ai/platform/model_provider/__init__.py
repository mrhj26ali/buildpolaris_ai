# src/buildpolaris_ai/platform/model_provider/__init__.py
"""
Model Provider layer — hexagonal port + config-driven adapter.

Usage:
    from buildpolaris_ai.platform.model_provider import get_model_provider

    provider = get_model_provider()
    result = await provider.structured_generate(prompt, MyResponseModel)
"""
from buildpolaris_ai.platform.model_provider.factory import get_model_provider
from buildpolaris_ai.platform.model_provider.instructor_adapter import InstructorProvider
from buildpolaris_ai.platform.model_provider.protocol import ModelProviderProtocol

__all__ = [
    "get_model_provider",
    "InstructorProvider",
    "ModelProviderProtocol",
]