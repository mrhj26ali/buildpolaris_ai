import json

import pytest

from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter


class FakeConnection:
    """
    Minimal asyncpg-compatible fake for fast unit tests.
    """

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.fetched: list[tuple[str, tuple]] = []

    async def execute(self, query: str, *args) -> None:
        self.executed.append((query, args))

    async def fetch(self, query: str, *args):
        self.fetched.append((query, args))
        return []


@pytest.mark.asyncio
async def test_upsert_parameterizes_docname_and_values():
    conn = FakeConnection()
    adapter = AGEAdapter(conn, graph_name="test_graph")

    malicious_docname = "RFI-1'}) DETACH DELETE n //"

    await adapter.upsert_document_node(
        doctype="RFI",
        docname=malicious_docname,
        properties={
            "project_id": "PROJ-1",
            "status": "Open",
        },
    )

    assert conn.fetched, "Expected exactly one Cypher query to be executed"

    query, args = conn.fetched[0]

    # No user-controlled values may be inlined into the query text.
    assert malicious_docname not in query
    assert "PROJ-1" not in query

    # The query must be parameterized through AGE agtype.
    assert "$1::ag_catalog.agtype" in query
    assert len(args) == 1

    params = json.loads(args[0])
    assert params["docname"] == malicious_docname

    values = list(params.values())
    assert "RFI" in values
    assert "PROJ-1" in values
    assert "Open" in values


@pytest.mark.asyncio
async def test_upsert_skips_unsafe_property_keys():
    conn = FakeConnection()
    adapter = AGEAdapter(conn, graph_name="test_graph")

    await adapter.upsert_document_node(
        doctype="RFI",
        docname="RFI-2",
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

    await adapter.enrich_with_graph_context([malicious_docname], limit=5)

    query, args = conn.fetched[0]

    assert malicious_docname not in query
    assert "LIMIT 5" in query

    params = json.loads(args[0])
    assert params["docnames"] == [malicious_docname]


def test_graph_name_must_be_safe():
    conn = FakeConnection()

    with pytest.raises(ValueError):
        AGEAdapter(conn, graph_name="bad-graph;")