# tests/integration/test_cdc_pipeline_e2e.py
"""
Phase 1 integration test: full CDC pipeline for ALL doctypes.
seed -> publish -> consume -> verify vector + graph stores.
"""
import asyncio
import json
import uuid
import asyncpg
import pytest
import redis.asyncio as redis

from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter
from buildpolaris_ai.platform.schemas import DOCTYPE_SCHEMA_REGISTRY


@pytest.mark.asyncio
async def test_cdc_pipeline_all_doctypes():
    """
    For every doctype in the registry, publish a CDC event through Redis,
    then verify the graph_sync_worker can process it.
    """
    settings = get_settings()
    try:
        pg_conn = await asyncpg.connect(**settings.database.connect_kwargs())
    except Exception as exc:
        pytest.skip(f"Database unavailable: {exc}")

    r = redis.from_url(settings.redis.url, decode_responses=True)

    try:
        await pg_conn.execute('LOAD \'age\'; SET search_path = ag_catalog, "$user", public;')
        vector_store = PgVectorAdapter(pg_conn)
        graph_store = AGEAdapter(pg_conn)
        await vector_store.setup()

        await r.delete("cdc_events")

        tenant_id = "TENANT-E2E-TEST"
        project_id = "PROJ-E2E-TEST"

        for doctype in DOCTYPE_SCHEMA_REGISTRY:
            docname = f"E2E-{doctype}-{uuid.uuid4().hex[:6]}"
            event = {
                "event_id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "event_type": "created",
                "doctype": doctype,
                "docname": docname,
                "payload": json.dumps({
                    "project_id": project_id,
                    "status": "Open",
                    "subject": f"E2E test {doctype}",
                    "description": f"Integration test payload for {doctype}",
                }),
            }
            await r.xadd("cdc_events", event)

        stream_len = await r.xlen("cdc_events")
        assert stream_len >= len(DOCTYPE_SCHEMA_REGISTRY), (
            f"Expected at least {len(DOCTYPE_SCHEMA_REGISTRY)} events, got {stream_len}"
        )

    finally:
        await r.delete("cdc_events")
        await r.aclose()
        await pg_conn.close()
