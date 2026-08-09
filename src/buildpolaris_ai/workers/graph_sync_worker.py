# src/buildpolaris_ai/workers/graph_sync_worker.py
import asyncio
import json
import uuid
import asyncpg
import ollama
import redis.asyncio as redis
import structlog
from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter

logger = structlog.get_logger()


async def generate_embedding(text: str) -> list[float]:
    client = ollama.AsyncClient()
    response = await client.embeddings(model='nomic-embed-text', prompt=text)
    return response['embedding']


def _decode_payload(raw):
    """Decode a CDC payload to a dict, tolerating single OR double JSON encoding."""
    payload = raw
    while isinstance(payload, str):
        payload = json.loads(payload)
    return payload


def _build_embedding_text(doctype: str, docname: str, payload: dict) -> str:
    """Build meaningful embedding text for any doctype."""
    parts = [f"Document ID: {docname}. Type: {doctype}."]

    if doctype == "RFI":
        parts.append(f"Subject: {payload.get('subject', '')}. {payload.get('description', '')}")
    elif doctype == "Task":
        parts.append(f"Title: {payload.get('title', '')}. {payload.get('description', '')}")
    elif doctype == "DailyLog":
        parts.append(f"Weather: {payload.get('weather', '')}. Delays: {payload.get('delays', '')}. {payload.get('description', '')}")
    elif doctype == "PunchListItem":
        parts.append(f"Status: {payload.get('status', '')}. Due: {payload.get('due_date', '')}. {payload.get('description', '')}")
    elif doctype == "IncidentReport":
        parts.append(f"OSHA: {payload.get('osha_classification', '')}. {payload.get('description', '')}")
    elif doctype == "SOVLine":
        parts.append(f"Budget: {payload.get('approved_budget', 0)}. Committed: {payload.get('committed_cost', 0)}. {payload.get('description', '')}")
    elif doctype == "ChangeEvent":
        parts.append(f"Category: {payload.get('category', '')}. Reason: {payload.get('outcome_reason', '')}. {payload.get('description', '')}")
    elif doctype == "ContractClause":
        parts.append(f"Type: {payload.get('clause_type', '')}. Risk: {payload.get('risk_flag', '')}. {payload.get('description', '')}")
    elif doctype == "ActionApprovalGate":
        parts.append(f"Ref: {payload.get('ref_doctype', '')}. Status: {payload.get('status', '')}. {payload.get('description', '')}")
    else:
        parts.append(payload.get('description', ''))

    return " ".join(parts)


async def process_event(
    pg_conn: asyncpg.Connection,
    vector_store: PgVectorAdapter,
    graph_store: AGEAdapter,
    msg_data: dict,
):
    event_id_str = msg_data['event_id']
    doctype = msg_data['doctype']
    docname = msg_data['docname']

    tenant_id = msg_data.get('tenant_id')
    if not tenant_id:
        logger.error("CDC event missing tenant_id, dropping event", event_id=event_id_str)
        return

    try:
        event_id = uuid.UUID(event_id_str)
    except ValueError:
        logger.error("Invalid UUID format", event_id=event_id_str)
        return

    payload = _decode_payload(msg_data['payload'])

    text_to_embed = _build_embedding_text(doctype, docname, payload)
    embedding = await generate_embedding(text_to_embed)

    try:
        async with pg_conn.transaction():
            await vector_store.upsert_embedding(str(event_id), tenant_id, embedding, payload)
            graph_props = {
                "project_id": payload.get("project_id", "N/A"),
                "status": payload.get("status", "N/A"),
            }
            await graph_store.upsert_document_node(doctype, docname, tenant_id, graph_props)
            logger.info(
                "Processed CDC Event",
                event_id=str(event_id),
                tenant_id=tenant_id,
                doctype=doctype,
                docname=docname,
            )
    except Exception as e:
        logger.error("Database transaction failed", event_id=str(event_id), tenant_id=tenant_id, error=str(e))
        raise


async def main():
    logger.info("Starting CDC Sync Worker...")
    settings = get_settings()
    pg_conn = await asyncpg.connect(**settings.database.connect_kwargs())
    r = redis.from_url(settings.redis.url, decode_responses=True)
    await pg_conn.execute('LOAD \'age\'; SET search_path = ag_catalog, "$user", public;')

    vector_store = PgVectorAdapter(pg_conn)
    graph_store = AGEAdapter(pg_conn)
    await vector_store.setup()

    logger.info("Worker initialized. Listening to 'cdc_events' stream...")
    last_id = "0-0"
    try:
        while True:
            messages = await r.xread({"cdc_events": last_id}, count=10, block=1000)
            if not messages:
                continue
            for stream, stream_messages in messages:
                for msg_id, msg_data in stream_messages:
                    last_id = msg_id
                    await process_event(pg_conn, vector_store, graph_store, msg_data)
    except KeyboardInterrupt:
        logger.info("Worker shutting down...")
    finally:
        await pg_conn.close()
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
