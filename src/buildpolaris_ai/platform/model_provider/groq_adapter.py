"""Groq adapter — fastest free LLM inference. Get key: https://console.groq.com/keys"""
from __future__ import annotations

import json
from typing import Type, TypeVar, Optional

import instructor
import structlog
from groq import AsyncGroq
from pydantic import BaseModel

from buildpolaris_ai.platform.model_provider.protocol import ModelProviderProtocol

logger = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)


class GroqProvider(ModelProviderProtocol):
    """Groq inference — extremely fast, free tier available."""

    def __init__(self, api_key: str, model: str = "llama-3.1-70b-versatile") -> None:
        self._client = instructor.from_groq(AsyncGroq(api_key=api_key))
        self._raw_client = AsyncGroq(api_key=api_key)
        self._model = model
        logger.info("Groq provider initialized", model=model)

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def default_model(self) -> str:
        return self._model

    async def structured_generate(
        self,
        prompt: str,
        response_model: Type[T],
        model: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        target = model or self._model
        try:
            result = await self._client.chat.completions.create(
                model=target,
                messages=[{"role": "user", "content": prompt}],
                response_model=response_model,
                temperature=temperature,
            )
            return result
        except Exception as e:
            logger.error("Groq structured_generate failed", error=str(e), model=target)
            raise

    async def generate_text(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        target = model or self._model
        try:
            response = await self._raw_client.chat.completions.create(
                model=target,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error("Groq generate_text failed", error=str(e), model=target)
            raise
