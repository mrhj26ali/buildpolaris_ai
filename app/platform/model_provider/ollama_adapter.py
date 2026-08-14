"""Ollama adapter â€” self-hosted fallback (ARCH Â§3.3 point 2: "a circuit
breaker falls back from a rate-limited or exhausted free-tier key to a
secondary provider or a locally-hosted Ollama model").
"""
from __future__ import annotations

import json
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel

from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelResponse

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class OllamaProvider:
    def __init__(self, base_url: str, model: str = "qwen2.5:3b-instruct") -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def default_model_version(self) -> str:
        return self._model_name

    async def complete(
        self, prompt: str, model_version: str | None = None,
        temperature: float = 0.2, max_tokens: int = 2048,
    ) -> ModelResponse:
        target = model_version or self._model_name
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": target, "prompt": prompt, "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return ModelResponse(
            text=data.get("response", ""),
            model_version=target,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    async def structured_complete(
        self, prompt: str, response_model: Type[T], model_version: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        schema_prompt = (
            f"{prompt}\n\nRespond with ONLY valid JSON matching this schema, "
            f"no prose, no code fences:\n{response_model.model_json_schema()}"
        )
        result = await self.complete(schema_prompt, model_version, temperature)
        text = result.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return response_model.model_validate(json.loads(text))

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        target = model_version or "nomic-embed-text"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/embeddings", json={"model": target, "prompt": text}
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    async def embed_batch(
        self, texts: list[str], model_version: str | None = None
    ) -> list[list[float]]:
        return [await self.embed(t, model_version) for t in texts]
