"""GraphStoreAdapter â€” the other half of RetrievalAdapter (ERD Â§4.4).

Vector search answers "what does this clause say"; graph traversal
answers "which subcontractors on delayed tasks" (FR-8.2's own example).
Nodes/edges are a MIRROR of MariaDB, never hand-curated (ERD Â§4.3) â€”
writes here only ever come from ingest/entity_mirror_service.py reacting
to a CDC event, never from a chat turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class GraphResult:
    node_key: str
    label: str
    mariadb_name: str
    properties: dict[str, Any] = field(default_factory=dict)
    relationship_path: list[str] = field(default_factory=list)


@runtime_checkable
class GraphStoreAdapter(Protocol):
    async def upsert_node(
        self, company: str, project: str | None, label: str, mariadb_name: str,
        properties: dict[str, Any],
    ) -> str:
        """Idempotent upsert (MERGE) keyed by (label, mariadb_name); returns node_key."""
        ...

    async def upsert_edge(
        self, company: str, edge_type: str, from_label: str, from_name: str,
        to_label: str, to_name: str,
    ) -> str:
        ...

    async def delete_node(self, company: str, label: str, mariadb_name: str) -> None:
        """UC-8.2/on_trash mirror â€” removes a node whose MariaDB source
        record was deleted, cascading its edges."""
        ...

    async def traverse(
        self, cypher: str, params: dict[str, Any], company: str, limit: int = 25,
    ) -> list[GraphResult]:
        """Scoped Cypher traversal (NFR-SEC.8: company is always enforced
        as a MATCH predicate, never left to the caller's query string
        alone) â€” see cypher_queries.py for the canned traversals callers
        should prefer over hand-writing Cypher per call site."""
        ...
