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
@pytest.mark.parametrize(
    "malicious_docname",
    [
        "RFI-1'); DETACH DELETE n //",
        "RFI-2\"}) RETURN 1 //",
        "RFI-3 $$ weird dollar quoting",
        "RFI-4'; DROP GRAPH polaris_knowledge_graph //",
        "RFI-5\nMERGE (n:Document {docname: 'evil'})",
    ],
)
async def test_malicious_docname_is_not_interpolated(malicious_docname: str):
    conn = FakeConnection()
    adapter = AGEAdapter(conn, graph_name="test_graph")

    await adapter.upsert_document_node(
        doctype="RFI",
        docname=malicious_docname,
        tenant_id="safe-tenant",
        properties={"project_id": "PROG-SEC"},
    )

    query, args = conn.fetched[0]

    assert malicious_docname not in query
    assert "$1::ag_catalog.agtype" in query

    params = json.loads(args[0])
    assert params["docname"] == malicious_docname


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malicious_value",
    [
        "Subject with ' single quote",
        "Subject with \" double quote",
        "Subject with $$ dollar quoting",
        "{malicious: true}",
        "value that tries to break SET syntax",
    ],
)
async def test_malicious_property_value_is_not_interpolated(malicious_value: str):
    conn = FakeConnection()
    adapter = AGEAdapter(conn, graph_name="test_graph")

    await adapter.upsert_document_node(
        doctype="RFI",
        docname="RFI-10",
        tenant_id="safe-tenant",
        properties={"subject": malicious_value},
    )

    query, args = conn.fetched[0]

    assert malicious_value not in query

    params = json.loads(args[0])
    values = list(params.values())
    assert malicious_value in values


@pytest.mark.asyncio
async def test_malicious_property_key_is_skipped():
    conn = FakeConnection()
    adapter = AGEAdapter(conn, graph_name="test_graph")

    unsafe_key = "n.doctype = 'x' //"
    await adapter.upsert_document_node(
        doctype="RFI",
        docname="RFI-11",
        tenant_id="safe-tenant",
        properties={
            unsafe_key: "evil",
            "project_id": "PROG-SEC",
        },
    )

    query, args = conn.fetched[0]

    assert unsafe_key not in query
    assert "n.doctype = 'x'" not in query

    params = json.loads(args[0])
    values = list(params.values())

    assert "evil" not in values
    # Be permissive: project id may appear under a generated prop_N key
    assert any("PROG-SEC" in str(v) for v in values)