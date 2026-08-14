"""EntityMirrorService â€” the FR-8.2 cross-cutting-graph half of ingestion.
Isolated from IngestionService the same way ARCH's ingest architecture
isolates the module from the orchestrator: this has no dependency on the
agent registry or RAG pipeline, and is triggered purely by BFF DocType
lifecycle hooks (after_insert/on_update/on_trash), never by a chat turn.
"""
from __future__ import annotations

import asyncpg

from app.gateway.schemas.graph_sync_event import GraphSyncEvent, GraphSyncResult
from app.ingest.projector import advance_cursor, should_process, to_cdc_event
from app.ingest.workers.graph_projection_worker import project_event
from app.observability.logging import get_logger
from app.platform.graph_store.adapter import GraphStoreAdapter

logger = get_logger(__name__)


class EntityMirrorService:
    def __init__(self, graph_store: GraphStoreAdapter, conn: asyncpg.Connection) -> None:
        self._graph_store = graph_store
        self._conn = conn

    async def sync(self, event: GraphSyncEvent) -> GraphSyncResult:
        if not await should_process(self._conn, event):
            logger.info(
                "graph_sync_event_stale_skipped", doctype=event.source_doctype,
                name=event.source_name, event_seq=event.event_seq,
            )
            return GraphSyncResult(accepted=False, reason="stale_or_out_of_order")

        cdc_event = to_cdc_event(event)
        node_key = await project_event(cdc_event, self._graph_store)
        await advance_cursor(self._conn, event)

        return GraphSyncResult(accepted=True, node_key=node_key)
