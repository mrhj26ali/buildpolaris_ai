"""OpenAI adapter â€” extensibility slot, same rationale as
anthropic_adapter.py. Not wired as primary or fallback in v1.
"""
from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel

from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelResponse

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class OpenAIProvider:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        import openai  # imported lazily â€” optional dependency in v1

        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model_name = model

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def default_model_version(self) -> str:
        return self._model_name

    async def complete(
        self, prompt: str, model_version: str | None = None,
        temperature: float = 0.2, max_tokens: int = 2048,
    ) -> ModelResponse:
        target = model_version or self._model_name
        response = await self._client.chat.completions.create(
            model=target, temperature=temperature, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return ModelResponse(
            text=response.choices[0].message.content or "",
            model_version=target,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )

    async def structured_complete(
        self, prompt: str, response_model: Type[T], model_version: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        target = model_version or self._model_name
        response = await self._client.beta.chat.completions.parse(
            model=target, temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
            response_format=response_model,
        )
        return response.choices[0].message.parsed

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        target = model_version or "text-embedding-3-small"
        response = await self._client.embeddings.create(model=target, input=text)
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str], model_version: str | None = None) -> list[list[float]]:
        target = model_version or "text-embedding-3-small"
        response = await self._client.embeddings.create(model=target, input=texts)
        return [d.embedding for d in response.data]
