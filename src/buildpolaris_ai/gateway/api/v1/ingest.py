"""v1 Ingest endpoint: receives CDC events from BFF."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from typing import Optional

import structlog

from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.schemas import CDCEvent
from buildpolaris_ai.platform.retrieval.connection import get_ai_db_conn
from buildpolaris_ai.platform.ingest.pipeline import IngestionPipeline
from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter

logger = structlog.get_logger()
router = APIRouter(tags=["v1 Ingest"])


@router.post("/ingest")
async def ingest_cdc_event(
    event: CDCEvent,
    conn=Depends(get_ai_db_conn),
    x_ingest_key: Optional[str] = Header(None, alias="X-Ingest-Key"),
):
    """System-to-system CDC ingest (ARCH §2.1 exception)."""
    settings = get_settings()

    # Verify ingest API key
    expected_key = settings.auth.ingest_api_key.get_secret_value()
    if x_ingest_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid ingest key")

    try:
        # Ingest into vector store
        pipeline = IngestionPipeline(conn)
        chunks_created = await pipeline.ingest_cdc_event(
            event.model_dump(), event.tenant_id
        )

        # Upsert graph node
        graph_store = AGEAdapter(conn)
        graph_props = {
            "project_id": event.project_id,
            "status": event.payload.get("status", "N/A"),
            "subject": event.payload.get("subject") or event.payload.get("title", ""),
        }
        await graph_store.upsert_document_node(
            event.doctype, event.docname, event.tenant_id, graph_props
        )

        return {
            "status": "ingested",
            "event_id": event.event_id,
            "chunks_created": chunks_created,
        }

    except Exception as e:
        logger.error("Ingest failed", event_id=event.event_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
