"""Publishes mock CDC events to Redis Stream for testing."""
import asyncio
import json

import asyncpg
import redis.asyncio as redis

from buildpolaris_ai.platform.config import get_settings


async def main():
    print("Starting Mock CDC Publisher...")
    settings = get_settings()
    pg_conn = await asyncpg.connect(**settings.database.connect_kwargs())
    r = redis.from_url(settings.redis.url, decode_responses=True)

    await r.delete("bp.cdc.events")
    print("Cleared 'bp.cdc.events' Redis Stream.")

    try:
        rows = await pg_conn.fetch(
            "SELECT id, tenant_id, doctype, docname, payload FROM mock_erpnext_docs LIMIT 20"
        )
        print(f"Publishing {len(rows)} events...")

        for row in rows:
            payload = row['payload']
            if isinstance(payload, str):
                payload = json.loads(payload)

            event = {
                "event_id": str(row['id']),
                "tenant_id": row['tenant_id'],
                "event_type": "created",
                "doctype": row['doctype'],
                "docname": row['docname'],
                "payload": json.dumps(payload, default=str),
            }
            await r.xadd("bp.cdc.events", event)

        print(f"Published {len(rows)} events.")
    finally:
        await pg_conn.close()
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
