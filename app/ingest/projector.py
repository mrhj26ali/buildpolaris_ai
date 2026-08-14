"""Translates the gateway-facing GraphSyncEvent (wire schema) into the
internal CDCEvent, applying the ordering/idempotency check against
graph_sync_cursor before handing off to graph_projection_worker. Kept
separate from entity_mirror_service.py so the "is this event stale/
out-of-order" decision is independently testable.
"""
from __future__ import annotations

import asyncpg

from app.gateway.schemas.graph_sync_event import GraphSyncEvent
from app.ingest.cdc_event_schema import CDCEvent
from app.observability.logging import get_logger

logger = get_logger(__name__)


async def should_process(conn: asyncpg.Connection, event: GraphSyncEvent) -> bool:
    """Guards against out-of-order delivery â€” if a later event for this
    source_doctype was already processed, a stale retry must be a no-op
    rather than overwriting newer graph state with older data."""
    row = await conn.fetchrow(
        "SELECT last_event_seq FROM graph_sync_cursor WHERE source_doctype = $1",
        event.source_doctype,
    )
    if row is None:
        return True
    return event.event_seq > row["last_event_seq"]


async def advance_cursor(conn: asyncpg.Connection, event: GraphSyncEvent) -> None:
    await conn.execute(
        """
        INSERT INTO graph_sync_cursor (source_doctype, last_synced_name, last_synced_at, last_event_seq)
        VALUES ($1, $2, now(), $3)
        ON CONFLICT (source_doctype) DO UPDATE
            SET last_synced_name = EXCLUDED.last_synced_name,
                last_synced_at = now(),
                last_event_seq = EXCLUDED.last_event_seq;
        """,
        event.source_doctype, event.source_name, event.event_seq,
    )


def to_cdc_event(event: GraphSyncEvent) -> CDCEvent:
    return CDCEvent(
        company=event.company, event_type=event.event_type, source_doctype=event.source_doctype,
        source_name=event.source_name, project=event.project, properties=event.properties,
        event_seq=event.event_seq,
    )
