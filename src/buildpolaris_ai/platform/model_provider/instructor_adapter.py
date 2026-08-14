"""Config-driven model provider adapter using instructor. Supports Ollama local."""
from __future__ import annotations

import inspect
from typing import Optional, Type, TypeVar

import instructor
import structlog
from pydantic import BaseModel, SecretStr

from buildpolaris_ai.platform.model_provider.protocol import ModelProviderProtocol

logger = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)


class InstructorProvider(ModelProviderProtocol):
    """Adapter for local providers (Ollama) via instructor."""

    def __init__(
        self,
        provider_id: str,
        api_key: SecretStr | None = None,
        base_url: str | None = None,
    ) -> None:
        self.provider_id = provider_id
        self._default_model = provider_id.split("/", 1)[-1] if "/" in provider_id else provider_id

        mode = instructor.Mode.JSON if provider_id.startswith("ollama/") else instructor.Mode.TOOLS
        kwargs: dict = {"mode": mode}
        if api_key:
            kwargs["api_key"] = api_key.get_secret_value()
        if base_url:
            kwargs["base_url"] = base_url

        self.client = instructor.from_provider(provider_id, **kwargs)
        logger.info("InstructorProvider initialized", provider_id=provider_id, mode=mode.value)

    @property
    def provider_name(self) -> str:
        return self.provider_id.split("/")[0] if "/" in self.provider_id else "unknown"

    @property
    def default_model(self) -> str:
        return self._default_model

    async def structured_generate(
        self,
        prompt: str,
        response_model: Type[T],
        model: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        target_model = model or self._default_model
        result_or_coro = self.client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": prompt}],
            response_model=response_model,
            temperature=temperature,
        )
        if inspect.isawaitable(result_or_coro):
            return await result_or_coro
        return result_or_coro

    async def generate_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        target_model = model or self._default_model
        result_or_coro = self.client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if inspect.isawaitable(result_or_coro):
            response = await result_or_coro
        else:
            response = result_or_coro
        # instructor returns validated model for structured; for text we get raw
        if hasattr(response, "content"):
            return response.content
        return str(response)
