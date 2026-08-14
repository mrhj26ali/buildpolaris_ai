"""Entity-mirror CDC event shape â€” POST /graph/sync (FR-8.2).

Mirrors app/ingest/cdc_event_schema.py's CDCEvent 1:1; kept as a separate
gateway-facing schema per NFR-EXT.1/ARCH Â§4.2 so the wire contract and the
internal processing model can diverge later without a breaking API
change.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class GraphSyncEvent(BaseModel):
    company: str
    event_type: Literal["after_insert", "on_update", "on_trash"]
    source_doctype: str  # 'Project' | 'Task' | 'RFI' | 'Commitment' | 'User' | 'Safety Incident'
    source_name: str
    project: str | None = None
    properties: dict[str, Any] = {}
    event_seq: int


class GraphSyncResult(BaseModel):
    accepted: bool
    node_key: str | None = None
    reason: str | None = None
