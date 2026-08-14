"""CDC sync worker: consumes events, chunks, embeds, stores."""
from __future__ import annotations

import asyncio
import json
import uuid

import asyncpg
import redis.asyncio as redis
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_not_exception_type

from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter
from buildpolaris_ai.platform.retrieval.chunker import ConstructionChunker
from buildpolaris_ai.platform.embedding.service import get_embedding_service

logger = structlog.get_logger()

STREAM_KEY = "bp.cdc.events"
DLQ_KEY = "bp.cdc.events.dlq"
PROCESSED_SET_KEY = "bp.cdc.processed"
MAX_RETRIES = 3


class CdcSyncWorker:
    """Processes CDC events into embeddings and graph nodes."""

    def __init__(self, pg_conn, redis_client) -> None:
        self.pg_conn = pg_conn
        self.redis = redis_client
        self.vector_store = PgVectorAdapter(pg_conn)
        self.graph_store = AGEAdapter(pg_conn)
        self.chunker = ConstructionChunker(chunk_size=512, chunk_overlap=64)
        self.embedding_service = get_embedding_service()

    async def setup(self) -> None:
        await self.pg_conn.execute('LOAD \'age\'; SET search_path = ag_catalog, "$user", public;')
        await self.vector_store.setup()

    async def _is_processed(self, event_id: str) -> bool:
        return bool(await self.redis.sismember(PROCESSED_SET_KEY, event_id))

    async def _mark_processed(self, event_id: str) -> None:
        await self.redis.sadd(PROCESSED_SET_KEY, event_id)

    async def _send_to_dlq(self, msg_id, msg_data, error) -> None:
        dlq_entry = dict(msg_data)
        dlq_entry["dlq_error"] = str(error)
        dlq_entry["original_msg_id"] = msg_id
        await self.redis.xadd(DLQ_KEY, dlq_entry)
        logger.error("Message sent to DLQ", msg_id=msg_id, error=str(error))

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_not_exception_type(ValueError),
        reraise=True,
    )
    async def _process_with_retry(self, msg_data: dict) -> None:
        event_id_str = msg_data.get("event_id", str(uuid.uuid4()))
        doctype = msg_data.get("doctype", "")
        docname = msg_data.get("docname", "")
        tenant_id = msg_data.get("tenant_id")

        if not tenant_id:
            raise ValueError("CDC event missing tenant_id")

        # Parse payload
        payload = msg_data.get("payload", {})
        if isinstance(payload, str):
            payload = json.loads(payload)

        # Build text for embedding
        text_parts = [f"Document ID: {docname}. Type: {doctype}."]
        for key in ["description", "subject", "title", "notes"]:
            if key in payload and payload[key]:
                text_parts.append(str(payload[key]))
        text = " ".join(text_parts)

        # Chunk and embed
        chunks = self.chunker.chunk_text(text, docname=docname, doctype=doctype, metadata=payload)

        for chunk in chunks:
            embedding = await self.embedding_service.embed_text(chunk.text)
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{docname}:{chunk.chunk_index}"))
            chunk_meta = {**chunk.metadata, "docname": docname, "doctype": doctype}
            await self.vector_store.upsert_embedding(chunk_id, tenant_id, embedding, chunk_meta)

        # Upsert graph node
        graph_props = {
            "project_id": payload.get("project_id", "N/A"),
            "status": payload.get("status", "N/A"),
            "subject": payload.get("subject") or payload.get("title", ""),
        }
        await self.graph_store.upsert_document_node(doctype, docname, tenant_id, graph_props)

        logger.info("CDC event processed", event_id=event_id_str, doctype=doctype, docname=docname)

    async def handle_message(self, msg_id, msg_data: dict) -> None:
        event_id = msg_data.get("event_id", msg_id)
        if await self._is_processed(event_id):
            logger.info("Skipping duplicate event", event_id=event_id)
            return

        try:
            await self._process_with_retry(msg_data)
            await self._mark_processed(event_id)
        except Exception as e:
            await self._send_to_dlq(msg_id, msg_data, e)

    async def run(self) -> None:
        await self.setup()
        logger.info("CDC Sync Worker started", stream=STREAM_KEY)
        last_id = "0-0"

        while True:
            messages = await self.redis.xread({STREAM_KEY: last_id}, count=10, block=1000)
            if not messages:
                continue
            for stream, stream_messages in messages:
                for msg_id, msg_data in stream_messages:
                    last_id = msg_id
                    await self.handle_message(msg_id, msg_data)
                    await self.redis.xdel(STREAM_KEY, msg_id)


async def main() -> None:
    settings = get_settings()
    pg_conn = await asyncpg.connect(**settings.database.connect_kwargs())
    r = redis.from_url(settings.redis.url, decode_responses=True)
    worker = CdcSyncWorker(pg_conn, r)
    try:
        await worker.run()
    finally:
        await pg_conn.close()
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
