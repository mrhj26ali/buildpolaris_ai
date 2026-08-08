import pytest
from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter


class FakeConn:
    def __init__(self):
        self.fetch_calls = []

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return []


@pytest.mark.asyncio
async def test_search_enforces_tenant_boundary_in_sql():
    mock_conn = FakeConn()

    adapter = PgVectorAdapter(mock_conn)
    await adapter.search([0.1]*768, "TENANT-ALPHA", limit=5)

    assert mock_conn.fetch_calls, "Expected fetch to be called"
    query, args = mock_conn.fetch_calls[0]

    # The query MUST explicitly filter by the provided tenant_id
    assert "WHERE tenant_id = $3" in query
    assert args[2] == "TENANT-ALPHA"  # $1 is embedding, $2 is limit, $3 is tenant_id
