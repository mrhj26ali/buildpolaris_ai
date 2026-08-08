from typing import Protocol


class VectorStoreProtocol(Protocol):
    """Hexagonal Port for Vector Store interactions."""

    async def upsert_embedding(self, doc_id: str, tenant_id: str, embedding: list[float], metadata: dict) -> None: 
        """Upsert an embedding, strictly scoped to a tenant."""
        ...
        
    async def search(self, query_embedding: list[float], tenant_id: str, limit: int = 3) -> list[dict]: 
        """Search for similar embeddings, strictly filtered by tenant_id."""
        ...