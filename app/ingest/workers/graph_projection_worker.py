"""Graph projection worker â€” applies one already-parsed CDC event to the
AGE graph store (ARCH Â§6.3 corrections note: "the entity mirror needed
its own worker, separate from the ingestion embedding worker, since they
run on entirely different triggers"). Ingestion triggers on a File
attach; graph projection triggers on any tracked DocType's lifecycle
hook, independent of whether that document has any attachments at all.
"""
from __future__ import annotations

from app.ingest.cdc_event_schema import CDCEvent
from app.observability.logging import get_logger
from app.platform.graph_store.adapter import GraphStoreAdapter

logger = get_logger(__name__)

# ERD Â§4.3 â€” which relationship this doctype's mirror also implies,
# beyond the node itself. Kept declarative so adding a new mirrored
# DocType + its edges is a data change here, not new control flow.
_EDGE_RULES: dict[str, list[tuple[str, str, str]]] = {
    # (edge_type, from_property_key_holding_related_name, to_label)
    "Task": [("HAS_TASK", "project", "Project"), ("ASSIGNED_TO", "assigned_to", "Person")],
    "RFI": [("RAISED_AGAINST", "task", "Task")],
    "Commitment": [("COMMITTED_TO", "vendor", "Person")],
    "Safety Incident": [("HAS_INCIDENT", "involved_person", "Person")],
}


async def project_event(event: CDCEvent, graph_store: GraphStoreAdapter) -> str | None:
    if event.event_type == "on_trash":
        await graph_store.delete_node(event.company, event.source_doctype, event.source_name)
        logger.info("graph_node_deleted", doctype=event.source_doctype, name=event.source_name)
        return None

    node_key = await graph_store.upsert_node(
        company=event.company, project=event.project, label=event.source_doctype,
        mariadb_name=event.source_name, properties=event.properties,
    )

    for edge_type, prop_key, to_label in _EDGE_RULES.get(event.source_doctype, []):
        related_name = event.properties.get(prop_key)
        if not related_name:
            continue
        try:
            await graph_store.upsert_edge(
                company=event.company, edge_type=edge_type, from_label=event.source_doctype,
                from_name=event.source_name, to_label=to_label, to_name=related_name,
            )
        except Exception as exc:  # noqa: BLE001 â€” a missing related node shouldn't fail the whole mirror
            logger.warning(
                "graph_edge_projection_skipped", edge_type=edge_type,
                from_name=event.source_name, to_name=related_name, error=str(exc),
            )

    logger.info("graph_node_projected", doctype=event.source_doctype, name=event.source_name)
    return node_key
