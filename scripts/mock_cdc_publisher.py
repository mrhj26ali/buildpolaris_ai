# scripts/mock_cdc_publisher.py
import asyncio
import json

import asyncpg
import redis.asyncio as redis

from buildpolaris_ai.platform.config import get_settings


async def main():
    print("Starting Mock CDC Publisher (Simulating BFF)...")
    settings = get_settings()

    pg_conn = await asyncpg.connect(**settings.database.connect_kwargs())
    r = redis.from_url(settings.redis.url, decode_responses=True)

    # Clear the stream to ensure a clean test run
    await r.delete("cdc_events")
    print("Cleared 'cdc_events' Redis Stream.")

    try:
        rows = await pg_conn.fetch("SELECT id, tenant_id, doctype, docname, payload FROM mock_erpnext_docs")
        print(f"Found {len(rows)} documents to publish to the event bus.")

        for row in rows:
            event = {
                "event_id": str(row['id']),
                "tenant_id": row['tenant_id'],
                "event_type": "created",
                "doctype": row['doctype'],
                "docname": row['docname'],
                "payload": json.dumps(row['payload']),
            }
            await r.xadd("cdc_events", event)

        print(f"Successfully published {len(rows)} events to Redis Stream 'cdc_events'.")
    finally:
        await pg_conn.close()
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())