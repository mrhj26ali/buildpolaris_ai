# src/buildpolaris_ai/platform/model_provider/protocol.py
from typing import Protocol, TypeVar, Type, runtime_checkable
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

@runtime_checkable
class ModelProviderProtocol(Protocol):
    """
    Hexagonal Port for LLM interactions.
    Ensures all model providers support structured generation via Pydantic models.
    """
    async def structured_generate(self, prompt: str, response_model: Type[T], model: str | None = None) -> T:
        """Generate a structured response using the LLM."""
        ...