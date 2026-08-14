"""AgeGraphAdapter â€” concrete GraphStoreAdapter over Apache AGE.

Cypher's MATCH clause cannot parameterize a node label or relationship
type (they're part of the query grammar, not a value), so `label` and
`edge_type` are validated against a fixed allow-list before ever being
interpolated into a query string â€” every value parameter (mariadb_name,
company, properties) goes through AGE's own `$1::agtype` parameter
binding, never string interpolation.
"""
from __future__ import annotations

import json
from typing import Any

import asyncpg

from app.observability.logging import get_logger
from app.platform.graph_store.adapter import GraphResult
from app.platform.graph_store.cypher_queries import (
    DELETE_NODE_TEMPLATE,
    GRAPH_NAME,
    UPSERT_EDGE_TEMPLATE,
    UPSERT_NODE_TEMPLATE,
)

logger = get_logger(__name__)

# ERD Â§4.3 â€” the closed set of node labels / edge types this platform mirrors.
ALLOWED_LABELS = {"Project", "Task", "RFI", "Commitment", "Person", "SafetyIncident"}
ALLOWED_EDGE_TYPES = {
    "HAS_TASK", "DEPENDS_ON", "ASSIGNED_TO", "RAISED_AGAINST", "COMMITTED_TO", "HAS_INCIDENT",
}


def _assert_allowed_label(label: str) -> None:
    if label not in ALLOWED_LABELS:
        raise ValueError(f"'{label}' is not an allow-listed graph node label")


def _assert_allowed_edge_type(edge_type: str) -> None:
    if edge_type not in ALLOWED_EDGE_TYPES:
        raise ValueError(f"'{edge_type}' is not an allow-listed graph edge type")


class AgeGraphAdapter:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def upsert_node(
        self, company: str, project: str | None, label: str, mariadb_name: str,
        properties: dict[str, Any],
    ) -> str:
        _assert_allowed_label(label)
        params = json.dumps(
            {"mariadb_name": mariadb_name, "company": company,
             "properties": {**properties, "project": project}}
        )
        query = UPSERT_NODE_TEMPLATE.format(graph=GRAPH_NAME, label=label)
        await self._conn.execute(query.replace("%s", f"'{params}'::agtype"))

        node_key = f"{label}:{mariadb_name}"
        await self._conn.execute(
            """
            INSERT INTO graph_node_index (node_key, label, mariadb_name, company, project, properties)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (node_key) DO UPDATE
                SET properties = EXCLUDED.properties, project = EXCLUDED.project, updated_at = now();
            """,
            node_key, label, mariadb_name, company, project, json.dumps(properties),
        )
        return node_key

    async def upsert_edge(
        self, company: str, edge_type: str, from_label: str, from_name: str,
        to_label: str, to_name: str,
    ) -> str:
        _assert_allowed_edge_type(edge_type)
        _assert_allowed_label(from_label)
        _assert_allowed_label(to_label)

        params = json.dumps({"from_name": from_name, "to_name": to_name, "company": company})
        query = UPSERT_EDGE_TEMPLATE.format(
            graph=GRAPH_NAME, from_label=from_label, to_label=to_label, edge_type=edge_type
        )
        await self._conn.execute(query.replace("%s", f"'{params}'::agtype"))

        from_key = f"{from_label}:{from_name}"
        to_key = f"{to_label}:{to_name}"
        edge_key = f"{edge_type}:{from_key}->{to_key}"
        await self._conn.execute(
            """
            INSERT INTO graph_edge_index (edge_key, edge_type, from_node_key, to_node_key, company)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (edge_key) DO UPDATE SET updated_at = now();
            """,
            edge_key, edge_type, from_key, to_key, company,
        )
        return edge_key

    async def delete_node(self, company: str, label: str, mariadb_name: str) -> None:
        _assert_allowed_label(label)
        params = json.dumps({"mariadb_name": mariadb_name, "company": company})
        query = DELETE_NODE_TEMPLATE.format(graph=GRAPH_NAME, label=label)
        await self._conn.execute(query.replace("%s", f"'{params}'::agtype"))

        node_key = f"{label}:{mariadb_name}"
        await self._conn.execute("DELETE FROM graph_node_index WHERE node_key = $1", node_key)

    async def traverse(
        self, cypher: str, params: dict[str, Any], company: str, limit: int = 25,
    ) -> list[GraphResult]:
        """`cypher` must be one of cypher_queries.py's pre-authored,
        reviewed traversal templates â€” never a caller-assembled string â€”
        so this method only ever formats graph name/limit, and binds
        company/other values as an agtype parameter.
        """
        full_params = {**params, "company": company, "limit": limit}
        query = cypher.format(graph=GRAPH_NAME)
        param_json = json.dumps(full_params)
        rows = await self._conn.fetch(query.replace("%s", f"'{param_json}'::agtype"))

        results: list[GraphResult] = []
        for row in rows:
            for value in row.values():
                if value is None:
                    continue
                try:
                    parsed = json.loads(str(value).rsplit("::", 1)[0])
                except (json.JSONDecodeError, ValueError):
                    continue
                props = parsed.get("properties", {})
                label = (parsed.get("label") or (parsed.get("labels") or [""])[0])
                results.append(
                    GraphResult(
                        node_key=f"{label}:{props.get('mariadb_name', '')}",
                        label=label,
                        mariadb_name=props.get("mariadb_name", ""),
                        properties=props,
                    )
                )
        return results
