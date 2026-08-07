# src/buildpolaris_ai/platform/retrieval/vector_store.py
from typing import Protocol

class VectorStoreProtocol(Protocol):
    """Hexagonal Port for Vector Store interactions."""
    async def upsert_embedding(self, doc_id: str, embedding: list[float], metadata: dict) -> None: ...
    async def search(self, query_embedding: list[float], limit: int = 3) -> list[dict]: ...