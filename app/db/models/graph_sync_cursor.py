"""Row model for `graph_sync_cursor` (migration 0007) â€” entity-mirror
idempotency tracking (ARCH Â§6.3 corrections note: "added graph_sync_cursor
model ... since the draft had no persistence for mirror-run tracking, only
ingestion tracking").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class GraphSyncCursor:
    source_doctype: str
    last_synced_name: str | None
    last_synced_at: datetime | None
    last_event_seq: int

    @classmethod
    def from_record(cls, record: Any) -> "GraphSyncCursor":
        return cls(**dict(record))
