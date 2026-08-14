"""Google Gemini adapter â€” primary provider (free-tier API key).

Uses the official google-genai SDK's structured-output support so
structured_complete() returns a real, schema-validated Pydantic instance
rather than a hand-parsed JSON blob.
"""
from __future__ import annotations

from typing import Type, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelResponse

logger = get_logger(__name__)
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


class GeminiProvider:
    def __init__(
        self, api_key: str, model: str = "gemini-2.0-flash",
        embedding_model: str = "text-embedding-004",
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model_name = model
        self._embedding_model = embedding_model
        logger.info("gemini_provider_initialized", model=model)

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def default_model_version(self) -> str:
        return self._model_name

    async def complete(
        self, prompt: str, model_version: str | None = None,
        temperature: float = 0.2, max_tokens: int = 2048,
    ) -> ModelResponse:
        target = model_version or self._model_name
        response = await self._client.aio.models.generate_content(
            model=target,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature, max_output_tokens=max_tokens
            ),
        )
        usage = getattr(response, "usage_metadata", None)
        return ModelResponse(
            text=response.text or "",
            model_version=target,
            prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            completion_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        )

    async def structured_complete(
        self, prompt: str, response_model: Type[T], model_version: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        target = model_version or self._model_name
        response = await self._client.aio.models.generate_content(
            model=target,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json",
                response_schema=response_model,
            ),
        )
        if getattr(response, "parsed", None) is not None:
            return response.parsed
        raw = _strip_code_fences(response.text or "")
        return response_model.model_validate_json(raw)

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        target = model_version or self._embedding_model
        response = await self._client.aio.models.embed_content(model=target, contents=text)
        return list(response.embeddings[0].values)

    async def embed_batch(
        self, texts: list[str], model_version: str | None = None
    ) -> list[list[float]]:
        target = model_version or self._embedding_model
        response = await self._client.aio.models.embed_content(model=target, contents=texts)
        return [list(e.values) for e in response.embeddings]
