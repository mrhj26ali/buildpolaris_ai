"""Row model for `document_chunks` (migration 0003).

Deliberately a plain dataclass, not a full ORM â€” this schema is small and
hand-reviewed (ERD Â§7); asyncpg + explicit SQL keeps the query shape
visible at the call site rather than hidden behind ORM-generated SQL.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class DocumentChunk:
    chunk_id: UUID
    company: str
    project: str
    source_doctype: str
    source_name: str
    file_id: str
    content_hash: str
    span_type: str  # 'page' | 'clause'
    span_start: int
    span_end: int
    chunk_text: str
    is_stale: bool
    created_at: datetime

    @classmethod
    def from_record(cls, record: Any) -> "DocumentChunk":
        return cls(**dict(record))
