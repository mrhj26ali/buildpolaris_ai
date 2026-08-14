"""ModelProviderAdapter â€” the port (ERD Â§4.4 class diagram, ratified).

NFR-EXT.2's sibling requirement for the LLM side: swapping a vendor or
adding a provider must not require touching every agent. Every concrete
provider (Gemini, Ollama, Anthropic, OpenAI) implements this one
interface; RagService and every agent depend only on this, never on a
concrete SDK.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Type, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class ModelResponse:
    text: str
    model_version: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


@runtime_checkable
class ModelProviderAdapter(Protocol):
    """Every method is model-version-explicit-capable: callers may pass a
    pinned model_version (NFR-AIGOV.2) rather than relying on an
    adapter-internal default that could silently change upstream."""

    @property
    def provider_name(self) -> str: ...

    @property
    def default_model_version(self) -> str: ...

    async def complete(
        self, prompt: str, model_version: str | None = None, temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> ModelResponse:
        """Free-text completion."""
        ...

    async def structured_complete(
        self, prompt: str, response_model: Type[T], model_version: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        """Structured generation constrained to a Pydantic schema â€” this is
        what RFIDraftingAgent and friends use so their output is a typed
        proposed_payload, not free text needing post-hoc parsing."""
        ...

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        """Single-text embedding."""
        ...

    async def embed_batch(
        self, texts: list[str], model_version: str | None = None
    ) -> list[list[float]]:
        ...
