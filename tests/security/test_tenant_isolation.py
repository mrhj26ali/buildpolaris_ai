
import json
import pytest
from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter


class FakeConn:
    def __init__(self):
        self.fetch_calls = []

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return []


@pytest.mark.asyncio
async def test_vector_search_enforces_tenant_boundary():
    mock_conn = FakeConn()

    adapter = PgVectorAdapter(mock_conn)

    # Attempt to search as TENANT-ALPHA
    await adapter.search([0.1]*768, "TENANT-ALPHA", limit=5)

    assert mock_conn.fetch_calls, "Expected fetch to be called"
    query, args = mock_conn.fetch_calls[0]

    assert "WHERE tenant_id = $3" in query
    assert args[2] == "TENANT-ALPHA"


@pytest.mark.asyncio
async def test_graph_enrichment_enforces_tenant_boundary():
    class FakeConn2:
        def __init__(self):
            self.fetched = []
        async def fetch(self, query, *args):
            self.fetched.append((query, args))
            return []
        async def execute(self, *args, **kwargs):
            return None

    mock_conn = FakeConn2()
    adapter = AGEAdapter(mock_conn, graph_name="test_graph")
    
    await adapter.enrich_with_graph_context(["RFI-1"], "TENANT-ALPHA", limit=3)
    
    query, args = mock_conn.fetched[0]
    params = json.loads(args[0])
    
    # Cypher MUST filter by tenant_id on both seed and related nodes
    assert "seed.tenant_id = $tenant_id" in query
    assert "related.tenant_id = $tenant_id" in query
    assert params["tenant_id"] == "TENANT-ALPHA"
