import json
import pytest
from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.fetched: list[tuple[str, tuple]] = []

    async def execute(self, query: str, *args) -> None:
        self.executed.append((query, args))

    async def fetch(self, query: str, *args):
        self.fetched.append((query, args))
        return []


@pytest.mark.asyncio
async def test_upsert_parameterizes_docname_and_tenant():
    conn = FakeConnection()
    adapter = AGEAdapter(conn, graph_name="test_graph")

    malicious_docname = "RFI-1'}) DETACH DELETE n //"

    await adapter.upsert_document_node(
        doctype="RFI",
        docname=malicious_docname,
        tenant_id="test-tenant",
        properties={"project_id": "PROJ-1", "status": "Open"},
    )

    query, args = conn.fetched[0]
    assert malicious_docname not in query
    assert "$1::ag_catalog.agtype" in query

    params = json.loads(args[0])
    assert params["docname"] == malicious_docname
    assert params["tenant_id"] == "test-tenant"


@pytest.mark.asyncio
async def test_enrich_parameterizes_and_filters_by_tenant():
    conn = FakeConnection()
    adapter = AGEAdapter(conn, graph_name="test_graph")

    await adapter.enrich_with_graph_context(["RFI-3"], tenant_id="tenant-A", limit=5)

    query, args = conn.fetched[0]
    assert "seed.tenant_id = $tenant_id" in query
    assert "related.tenant_id = $tenant_id" in query

    params = json.loads(args[0])
    assert params["tenant_id"] == "tenant-A"


def test_graph_name_must_be_safe():
    conn = FakeConnection()
    with pytest.raises(ValueError):
        AGEAdapter(conn, graph_name="bad-graph;")


@pytest.mark.asyncio
async def test_upsert_skips_unsafe_property_keys():
    conn = FakeConnection()
    adapter = AGEAdapter(conn, graph_name="test_graph")

    await adapter.upsert_document_node(
        doctype="RFI",
        docname="RFI-2",
        tenant_id="test-tenant",
        properties={
            "bad$key": "x",
            "project_id": "p",
        },
    )

    query, args = conn.fetched[0]

    assert "bad$key" not in query

    params = json.loads(args[0])
    values = list(params.values())

    # Unsafe key's value should not become a query parameter.
    assert "x" not in values

    # Safe key should still be persisted.
    assert "p" in values


@pytest.mark.asyncio
async def test_enrich_parameterizes_docnames():
    conn = FakeConnection()
    adapter = AGEAdapter(conn, graph_name="test_graph")

    malicious_docname = "RFI-3'}) RETURN 1 //"

    await adapter.enrich_with_graph_context([malicious_docname], tenant_id="test-tenant", limit=5)

    query, args = conn.fetched[0]

    assert malicious_docname not in query
    assert "LIMIT 5" in query

    params = json.loads(args[0])
    assert params["docnames"] == [malicious_docname]