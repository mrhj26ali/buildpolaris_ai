"""Google Gemini adapter using the official google-genai SDK."""
from __future__ import annotations

from typing import Type, TypeVar

import structlog
from google import genai
from google.genai import types
from pydantic import BaseModel

from buildpolaris_ai.platform.model_provider.protocol import ModelProviderProtocol

logger = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class GeminiProvider(ModelProviderProtocol):
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model_name = model
        logger.info("Gemini provider initialized (google-genai)", model=model)

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return self._model_name

    async def structured_generate(
        self, prompt: str, response_model: Type[T],
        model: str | None = None, temperature: float = 0.1,
    ) -> T:
        target = model or self._model_name
        try:
            response = await self._client.aio.models.generate_content(
                model=target,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                    response_schema=response_model,
                ),
            )
            # google-genai automatically parses into the schema if possible
            if hasattr(response, "parsed") and response.parsed is not None:
                return response.parsed
            
            # Fallback to manual parsing if the SDK didn't auto-parse
            raw = _strip_code_fences(response.text or "")
            return response_model.model_validate_json(raw)
        except Exception as e:
            logger.error("Gemini structured_generate failed", error=str(e), model=target)
            raise

    async def generate_text(
        self, prompt: str, model: str | None = None,
        temperature: float = 0.1, max_tokens: int = 2048,
    ) -> str:
        target = model or self._model_name
        try:
            response = await self._client.aio.models.generate_content(
                model=target,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            return response.text or ""
        except Exception as e:
            logger.error("Gemini generate_text failed", error=str(e), model=target)
            raise
