# src/buildpolaris_ai/platform/retrieval/graph_store.py
from typing import Protocol

class GraphStoreProtocol(Protocol):
    """Hexagonal Port for Graph Store interactions."""
    async def upsert_document_node(self, doctype: str, docname: str, properties: dict) -> None: ...