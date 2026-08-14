"""Row model for `embeddings` (migration 0004)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class Embedding:
    embedding_id: UUID
    chunk_id: UUID
    embedding: list[float]
    model_version: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: Any) -> "Embedding":
        data = dict(record)
        vec = data.get("embedding")
        if vec is not None and not isinstance(vec, list):
            data["embedding"] = list(vec)
        return cls(**data)
