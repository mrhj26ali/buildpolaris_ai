# src/buildpolaris_ai/platform/retrieval/vector_store.py
from typing import Protocol

class VectorStoreProtocol(Protocol):
    """Hexagonal Port for Vector Store interactions."""
    async def upsert_embedding(self, doc_id: str, embedding: list[float], metadata: dict) -> None: ...