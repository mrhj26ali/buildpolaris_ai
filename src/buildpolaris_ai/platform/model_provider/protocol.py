"""Hexagonal Port for LLM interactions."""
from __future__ import annotations

from typing import Protocol, TypeVar, Type, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class ModelProviderProtocol(Protocol):
    """All model providers must support structured generation."""

    async def structured_generate(
        self,
        prompt: str,
        response_model: Type[T],
        model: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        ...

    async def generate_text(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        ...

    @property
    def provider_name(self) -> str:
        ...

    @property
    def default_model(self) -> str:
        ...
