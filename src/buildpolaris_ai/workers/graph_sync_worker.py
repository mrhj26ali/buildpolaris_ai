# src/buildpolaris_ai/workers/graph_sync_worker.py
import asyncio
import asyncpg
import redis.asyncio as redis
import json
import os
import uuid
import ollama
import structlog

from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter

logger = structlog.get_logger()

DB_USER = os.getenv("DB_USER", "polaris_ai")
DB_PASSWORD = os.getenv("DB_PASSWORD", "polaris_ai_dev_password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "polaris_knowledge")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

async def generate_embedding(text: str) -> list[float]:
    client = ollama.AsyncClient()
    response = await client.embeddings(model='nomic-embed-text', prompt=text)
    return response['embedding']

async def process_event(pg_conn: asyncpg.Connection, vector_store: PgVectorAdapter, graph_store: AGEAdapter, msg_data: dict):
    event_id_str = msg_data['event_id']
    doctype = msg_data['doctype']
    docname = msg_data['docname']
    
    try:
        event_id = uuid.UUID(event_id_str)
    except ValueError:
        logger.error("Invalid UUID format", event_id=event_id_str)
        return
    
    payload = msg_data['payload']
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, str):
        payload = json.loads(payload)
        
    # CRITICAL FIX: Include the docname in the embedded text!
    # Without this, vector search cannot find documents by their specific ID.
    subject = payload.get('subject') or payload.get('title') or ''
    description = payload.get('description', '')
    text_to_embed = f"Document ID: {docname}. Type: {doctype}. Subject: {subject}. Description: {description}"
    
    embedding = await generate_embedding(text_to_embed)
    
    try:
        async with pg_conn.transaction():
            await vector_store.upsert_embedding(str(event_id), embedding, payload)
            
            graph_props = {
                "project_id": payload.get("project_id", "N/A"),
                "status": payload.get("status", "N/A")
            }
            await graph_store.upsert_document_node(doctype, docname, graph_props)
            
        logger.info("Processed CDC Event", event_id=str(event_id), doctype=doctype, docname=docname)
    except Exception as e:
        logger.error("Database transaction failed", event_id=str(event_id), error=str(e))
        raise

async def main():
    logger.info("🚀 Starting CDC Sync Worker...")
    
    pg_conn = await asyncpg.connect(user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT, database=DB_NAME)
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    await pg_conn.execute('LOAD \'age\'; SET search_path = ag_catalog, "$user", public;')
    
    vector_store = PgVectorAdapter(pg_conn)
    graph_store = AGEAdapter(pg_conn)
    
    await vector_store.setup()
    
    logger.info("✅ Worker initialized. Listening to 'cdc_events' stream...")
    
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
        logger.info("🛑 Worker shutting down...")
    finally:
        await pg_conn.close()
        await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())