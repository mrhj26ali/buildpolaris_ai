"""Anthropic adapter â€” extensibility slot (ARCH Â§3.3 point 2: "room for
AnthropicAdapter/OpenAIAdapter alongside it"). Not wired as primary or
fallback in v1 (no free-tier key path), but implements the same port so a
tenant can be pinned to it (NFR-AIGOV.2) the moment a key is configured,
with zero changes anywhere else in the codebase.
"""
from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel

from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelResponse

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class AnthropicProvider:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        import anthropic  # imported lazily â€” optional dependency in v1

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model_name = model

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def default_model_version(self) -> str:
        return self._model_name

    async def complete(
        self, prompt: str, model_version: str | None = None,
        temperature: float = 0.2, max_tokens: int = 2048,
    ) -> ModelResponse:
        target = model_version or self._model_name
        response = await self._client.messages.create(
            model=target, max_tokens=max_tokens, temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return ModelResponse(
            text=text, model_version=target,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )

    async def structured_complete(
        self, prompt: str, response_model: Type[T], model_version: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        schema_prompt = (
            f"{prompt}\n\nRespond with ONLY valid JSON matching this schema:\n"
            f"{response_model.model_json_schema()}"
        )
        result = await self.complete(schema_prompt, model_version, temperature)
        return response_model.model_validate_json(result.text)

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        raise NotImplementedError(
            "Anthropic does not offer an embeddings endpoint â€” pin embedding "
            "to a different provider via config, not this adapter."
        )

    async def embed_batch(self, texts: list[str], model_version: str | None = None) -> list[list[float]]:
        raise NotImplementedError("see embed()")
