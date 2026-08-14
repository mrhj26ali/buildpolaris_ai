"""Row model for `graph_node_index` (migration 0005) â€” the relational
index over the AGE graph, mirroring MariaDB entities via DocType lifecycle
hooks (ERD Â§4.3), never hand-curated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class GraphNode:
    node_key: str  # '{label}:{mariadb_name}'
    label: str
    mariadb_name: str
    company: str
    project: str | None
    properties: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None

    @staticmethod
    def make_key(label: str, mariadb_name: str) -> str:
        return f"{label}:{mariadb_name}"

    @classmethod
    def from_record(cls, record: Any) -> "GraphNode":
        return cls(**dict(record))
