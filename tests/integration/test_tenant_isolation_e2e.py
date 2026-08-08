import os
import pytest
import asyncpg
from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter

DB_USER = os.getenv("DB_USER", "polaris_ai")
DB_PASSWORD = os.getenv("DB_PASSWORD", "polaris_ai_dev_password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "polaris_knowledge")

TEST_GRAPH_NAME = "polaris_ai_tenant_test_graph"

async def _get_connection():
    try:
        return await asyncpg.connect(user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT, database=DB_NAME)
    except Exception as exc:
        pytest.skip(f"Database unavailable: {exc}")


@pytest.mark.asyncio
async def test_cross_tenant_data_leakage_is_impossible():
    conn = await _get_connection()
    try:
        # Setup
        await conn.execute("LOAD 'age';")
        await conn.execute('SET search_path = ag_catalog, "$user", public;')
        try:
            await conn.execute(f"SELECT * FROM ag_catalog.drop_graph('{TEST_GRAPH_NAME}', true);")
        except Exception: pass
        await conn.execute(f"SELECT * FROM ag_catalog.create_graph('{TEST_GRAPH_NAME}');")
        
        vec_adapter = PgVectorAdapter(conn)
        graph_adapter = AGEAdapter(conn, graph_name=TEST_GRAPH_NAME)
        await vec_adapter.setup()
        
        # Clear vector table for this test
        await conn.execute("DELETE FROM public.document_embeddings WHERE tenant_id LIKE 'TEST-TENANT-%';")

        # 1. Insert data for TENANT-A
        await vec_adapter.upsert_embedding("11111111-1111-1111-1111-111111111111", "TEST-TENANT-A", [0.1]*768, {"docname": "RFI-A"})
        await graph_adapter.upsert_document_node("RFI", "RFI-A", "TEST-TENANT-A", {"subject": "Tenant A Secret"})

        # 2. Insert data for TENANT-B
        await vec_adapter.upsert_embedding("22222222-2222-2222-2222-222222222222", "TEST-TENANT-B", [0.1]*768, {"docname": "RFI-B"})
        await graph_adapter.upsert_document_node("RFI", "RFI-B", "TEST-TENANT-B", {"subject": "Tenant B Secret"})

        # 3. TENANT-A searches vectors
        vec_results = await vec_adapter.search([0.1]*768, "TEST-TENANT-A", limit=5)
        assert len(vec_results) == 1
        assert vec_results[0]["metadata"]["docname"] == "RFI-A"

        # 4. TENANT-A searches graph (should not see RFI-B)
        graph_results = await graph_adapter.enrich_with_graph_context(["RFI-A", "RFI-B"], "TEST-TENANT-A", limit=5)
        for res in graph_results:
            assert res["docname"] != "RFI-B"

    finally:
        try:
            await conn.execute(f"SELECT * FROM ag_catalog.drop_graph('{TEST_GRAPH_NAME}', true);")
        except Exception: pass
        await conn.execute("DELETE FROM public.document_embeddings WHERE tenant_id LIKE 'TEST-TENANT-%';")
        await conn.close()
