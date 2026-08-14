"""Row model for `graph_edge_index` (migration 0006)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class GraphEdge:
    edge_key: str
    edge_type: str
    from_node_key: str
    to_node_key: str
    company: str
    updated_at: datetime | None = None

    @staticmethod
    def make_key(edge_type: str, from_node_key: str, to_node_key: str) -> str:
        return f"{edge_type}:{from_node_key}->{to_node_key}"

    @classmethod
    def from_record(cls, record: Any) -> "GraphEdge":
        return cls(**dict(record))
