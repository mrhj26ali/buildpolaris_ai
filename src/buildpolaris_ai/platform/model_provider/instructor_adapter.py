# src/buildpolaris_ai/platform/model_provider/instructor_adapter.py
"""
Config-driven model provider adapter using instructor's multi-provider support.

Replaces the old hardcoded ollama_adapter.py (Decision Log #6).
Supports any provider instructor supports:
  - Local:  "ollama/qwen2.5:3b-instruct"
  - API:    "google/gemini-2.5-flash", "anthropic/claude-...", "openai/gpt-..."

Provider selection is a config change, not a code change.

NOTE on async: instructor.from_provider() returns a SYNCHRONOUS client for
some providers (notably Ollama), whose create() returns the validated model
directly instead of a coroutine. structured_generate() handles both sync and
async clients defensively via inspect.isawaitable.
"""
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
    """
    Hexagonal Adapter for LLM providers via instructor.

    A single adapter satisfies ModelProviderProtocol for ALL providers.
    The provider_id string (e.g., "ollama/qwen2.5:3b-instruct") determines
    which backend is used — no per-provider classes needed.
    """

    def __init__(
        self,
        provider_id: str,
        api_key: SecretStr | None = None,
        base_url: str | None = None,
    ) -> None:
        self.provider_id = provider_id
        self._default_model = self._extract_model(provider_id)

        # Resolve the appropriate instructor mode for this provider
        mode = self._resolve_mode()

        # Build kwargs for from_provider
        kwargs: dict = {"mode": mode}
        if api_key:
            kwargs["api_key"] = api_key.get_secret_value()
        if base_url:
            kwargs["base_url"] = base_url

        self.client = instructor.from_provider(provider_id, **kwargs)

        logger.info(
            "Model provider initialized",
            provider_id=provider_id,
            default_model=self._default_model,
            mode=mode.value,
        )

    @staticmethod
    def _extract_model(provider_id: str) -> str:
        """
        Extract the model name from a provider_id.

        Examples:
            "ollama/qwen2.5:3b-instruct" -> "qwen2.5:3b-instruct"
            "google/gemini-2.5-flash"    -> "gemini-2.5-flash"
        """
        parts = provider_id.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(
                f"Invalid provider_id format: {provider_id!r}. "
                f"Expected 'provider/model' (e.g., 'ollama/qwen2.5:3b-instruct')."
            )
        return parts[1]

    def _resolve_mode(self) -> instructor.Mode:
        """
        Resolve the instructor extraction mode based on the provider.

        CRITICAL: Ollama requires JSON mode to prevent crashes when the model
        outputs plain text instead of tool calls. This preserves the fix from
        the original ollama_adapter.py.

        Other providers (Gemini, Anthropic, OpenAI) use TOOLS mode by default,
        which is more reliable for structured output extraction.
        """
        if self.provider_id.startswith("ollama/"):
            return instructor.Mode.JSON
        return instructor.Mode.TOOLS

    async def structured_generate(
        self,
        prompt: str,
        response_model: Type[T],
        model: Optional[str] = None,
    ) -> T:
        """
        Generate a structured response using the LLM.

        Defensive against both sync and async instructor clients:
        from_provider() returns a sync client for some providers (notably
        Ollama), whose create() yields the validated model directly rather
        than a coroutine. We await only when the result is actually awaitable.
        """
        target_model = model or self._default_model

        result_or_coro = self.client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": prompt}],
            response_model=response_model,
        )

        if inspect.isawaitable(result_or_coro):
            return await result_or_coro
        return result_or_coro