# scripts/mock_cdc_publisher.py
import asyncio
import asyncpg
import redis.asyncio as redis
import json
import os

DB_USER = os.getenv("DB_USER", "polaris_ai")
DB_PASSWORD = os.getenv("DB_PASSWORD", "polaris_ai_dev_password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "polaris_knowledge")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

async def main():
    print("📡 Starting Mock CDC Publisher (Simulating BFF)...")
    
    pg_conn = await asyncpg.connect(user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT, database=DB_NAME)
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    # Clear the stream to ensure a clean test run
    await r.delete("cdc_events")
    print("🗑️ Cleared 'cdc_events' Redis Stream.")

    try:
        rows = await pg_conn.fetch("SELECT id, tenant_id, doctype, docname, payload FROM mock_erpnext_docs")
        print(f"📦 Found {len(rows)} documents to publish to the event bus.")

        for row in rows:
            event = {
                "event_id": str(row['id']),
                "tenant_id": row['tenant_id'],
                "event_type": "created",
                "doctype": row['doctype'],
                "docname": row['docname'],
                "payload": json.dumps(row['payload'])
            }
            await r.xadd("cdc_events", event)

        print(f"✅ Successfully published {len(rows)} events to Redis Stream 'cdc_events'.")
    finally:
        await pg_conn.close()
        await r.aclose()  # FIX: Use aclose() to resolve the DeprecationWarning

if __name__ == "__main__":
    asyncio.run(main())