import json
import os

import asyncpg
import pytest

from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter

DB_USER = os.getenv("DB_USER", "polaris_ai")
DB_PASSWORD = os.getenv("DB_PASSWORD", "polaris_ai_dev_password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "polaris_knowledge")

TEST_GRAPH_NAME = "polaris_ai_test_graph"


async def _get_connection():
    try:
        return await asyncpg.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
        )
    except Exception as exc:
        pytest.skip(f"Database unavailable: {exc}")


@pytest.mark.asyncio
async def test_parameterized_cypher_executes_against_real_age():
    conn = await _get_connection()

    try:
        await conn.execute("LOAD 'age';")
        await conn.execute('SET search_path = ag_catalog, "$user", public;')

        try:
            await conn.execute(
                f"SELECT * FROM ag_catalog.drop_graph('{TEST_GRAPH_NAME}', true);"
            )
        except Exception:
            pass

        await conn.execute(
            f"SELECT * FROM ag_catalog.create_graph('{TEST_GRAPH_NAME}');"
        )

        adapter = AGEAdapter(conn, graph_name=TEST_GRAPH_NAME)

        malicious_docname = "RFI-1000'}) DETACH DELETE n //"
        malicious_subject = "Subject with ' quotes and $$ dollars"

        await adapter.upsert_document_node(
            doctype="RFI",
            docname=malicious_docname,
            properties={
                "project_id": "PROJ-SEC",
                "status": "Open",
                "subject": malicious_subject,
            },
        )

        count_query = f"""
SELECT * FROM ag_catalog.cypher('{TEST_GRAPH_NAME}', $$
MATCH (n:Document {{docname: $docname}})
RETURN count(n) AS node_count
$$, $1::ag_catalog.agtype) AS (node_count ag_catalog.agtype);
"""

        rows = await conn.fetch(
            count_query,
            json.dumps({"docname": malicious_docname}),
        )

        assert rows, "Expected count query to return one row"

        raw_count = str(rows[0]["node_count"]).strip().strip('"')
        assert int(raw_count) == 1

        enriched = await adapter.enrich_with_graph_context(
            [malicious_docname],
            limit=10,
        )

        assert isinstance(enriched, list)

    finally:
        try:
            await conn.execute(
                f"SELECT * FROM ag_catalog.drop_graph('{TEST_GRAPH_NAME}', true);"
            )
        except Exception:
            pass

        await conn.close()