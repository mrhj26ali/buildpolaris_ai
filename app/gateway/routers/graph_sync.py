"""POST /graph/sync â€” FR-8.2's entity mirror ingress. Called by BFF
DocType lifecycle hooks (after_insert/on_update/on_trash) on every
tracked entity, independent of ingest.py's file-attachment trigger.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db.postgres import get_pool
from app.exceptions import ScopeMismatchError
from app.gateway.auth.scope_assertion import ScopeAssertion, verify_scope_assertion
from app.gateway.auth.service_credential import verify_service_credential
from app.gateway.schemas.graph_sync_event import GraphSyncEvent, GraphSyncResult
from app.ingest.entity_mirror_service import EntityMirrorService
from app.observability.logging import get_logger
from app.platform.graph_store.age_adapter import AgeGraphAdapter

logger = get_logger(__name__)

router = APIRouter(
    prefix="/graph", tags=["graph-sync"], dependencies=[Depends(verify_service_credential)]
)


@router.post("/sync", response_model=GraphSyncResult)
async def sync_graph_event(
    body: GraphSyncEvent,
    assertion: ScopeAssertion = Depends(verify_scope_assertion),
) -> GraphSyncResult:
    if body.company != assertion.company:
        raise ScopeMismatchError("graph sync event company does not match asserted scope")

    async with get_pool().acquire() as conn:
        service = EntityMirrorService(AgeGraphAdapter(conn), conn)
        result = await service.sync(body)

    logger.info(
        "graph_sync_processed", doctype=body.source_doctype, name=body.source_name,
        accepted=result.accepted,
    )
    return result
