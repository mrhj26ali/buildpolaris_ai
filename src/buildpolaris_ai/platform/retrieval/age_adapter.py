from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog

from buildpolaris_ai.platform.retrieval.graph_store import GraphStoreProtocol

logger = structlog.get_logger()

_GRAPH_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROPERTY_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Keys that must not be accepted from caller-supplied properties because
# the adapter controls them explicitly.
_RESERVED_INPUT_KEYS = {"docname", "doctype", "tenant_id"}

# Keys that should never be emitted as dynamic SET clauses inside the query.
_RESERVED_BUILD_KEYS = {"docname"}


def _json_safe(value: Any) -> Any:
    """
    Convert Python values into JSON-serializable equivalents.

    This is used before casting parameters to AGE agtype.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    return str(value)


def _to_graph_property(value: Any) -> Any:
    """
    Normalize a value for use as an AGE node property.

    Scalars stay scalar. Structured values are serialized to JSON strings
    because graph node properties should remain simple and query-safe.
    """
    normalized = _json_safe(value)
    if isinstance(normalized, (dict, list)):
        return json.dumps(normalized, ensure_ascii=False)
    return normalized


def _parse_agtype_scalar(value: Any) -> Any:
    """
    Parse scalar agtype values returned over asyncpg.

    In many AGE/asyncpg setups these arrive as string-encoded values.
    We try JSON parsing first, then fall back to a quoted-string strip.
    """
    if value is None:
        return None

    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value.strip('"')

    return value


class AGEAdapter(GraphStoreProtocol):
    """
    Hexagonal Adapter for Apache AGE.

    Security model:
    - graph name is validated as a safe identifier
    - property keys are validated as safe identifiers
    - all values are passed through agtype parameters
    - no user-influenced value is interpolated into Cypher text
    """

    def __init__(
        self,
        conn: Any,
        graph_name: str = "polaris_knowledge_graph",
    ) -> None:
        self.conn = conn
        self._graph_name = self._validate_identifier(graph_name)
        self._age_loaded = False

    @staticmethod
    def _validate_identifier(value: str) -> str:
        """
        Validate identifiers that must appear directly in query text,
        such as the graph name.

        This is deliberately conservative.
        """
        if not isinstance(value, str) or not _GRAPH_NAME_PATTERN.match(value):
            raise ValueError(f"Unsafe or invalid identifier: {value!r}")
        return value

    async def _ensure_age_loaded(self) -> None:
        """
        Ensure AGE is loaded in this session.

        This is idempotent per adapter instance and keeps the adapter usable
        in tests and runtime workers alike.
        """
        if not self._age_loaded:
            await self.conn.execute("LOAD 'age';")
            await self.conn.execute('SET search_path = ag_catalog, "$user", public;')
            self._age_loaded = True

    async def _execute_cypher(
        self,
        query: str,
        params: dict[str, Any],
    ) -> list[Any]:
        """
        Execute a parameterized Cypher query through AGE.

        The second argument to ag_catalog.cypher is the Cypher text.
        The third argument is an agtype parameter map.
        """
        await self._ensure_age_loaded()
        serialized_params = json.dumps(_json_safe(params), ensure_ascii=False)
        return await self.conn.fetch(query, serialized_params)

    def _build_upsert_query(
        self,
        properties: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """
        Build a parameterized upsert query.

        Returns:
        - query text containing only validated identifiers and parameter refs
        - parameter dictionary to serialize as agtype
        """
        set_clauses: list[str] = []
        params: dict[str, Any] = {}
        index = 0

        for raw_key, raw_value in properties.items():
            key = str(raw_key)

            if key in _RESERVED_BUILD_KEYS:
                continue

            if not _PROPERTY_KEY_PATTERN.match(key):
                logger.warning(
                    "Skipping unsafe Apache AGE property key",
                    property_key=key,
                )
                continue

            param_name = f"prop_{index}"
            index += 1
            set_clauses.append(f"n.{key} = ${param_name}")
            params[param_name] = _to_graph_property(raw_value)

        if not set_clauses:
            set_sql = "n.docname = $docname"
        else:
            set_sql = ", ".join(set_clauses)

        query = f"""
    SELECT * FROM ag_catalog.cypher('{self._graph_name}', $$
    MERGE (n:Document {{docname: $docname, tenant_id: $tenant_id}})
    SET {set_sql}
    RETURN n
    $$, $1::ag_catalog.agtype) AS (n ag_catalog.agtype);
    """
        return query, params

    async def upsert_document_node(
        self,
        doctype: str,
        docname: str,
        tenant_id: str,
        properties: dict[str, Any],
    ) -> None:
        """
        Parameterized upsert of a Document node with tenant scoping.
        """
        clean_input = properties or {}
        clean_properties = {
            k: v
            for k, v in clean_input.items()
            if k not in _RESERVED_INPUT_KEYS
        }

        merged_properties: dict[str, Any] = {
            "doctype": doctype,
            "tenant_id": str(tenant_id),
            **clean_properties,
        }

        query, property_params = self._build_upsert_query(merged_properties)

        params: dict[str, Any] = {
            "docname": str(docname),
            "tenant_id": str(tenant_id),
        }
        params.update(property_params)

        try:
            await self._execute_cypher(query, params)
        except Exception as exc:
            logger.error(
                "AGE upsert failed",
                doctype=doctype,
                docname=docname,
                tenant_id=tenant_id,
                error=str(exc),
            )
            raise

    async def enrich_with_graph_context(
        self,
        seed_docnames: list[str],
        tenant_id: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Hybrid RAG Step 2:
        Take docnames found by vector search and traverse immediate graph
        relationships to enrich retrieval context.
        """
        if not seed_docnames:
            return []

        try:
            limit_value = int(limit)
        except (TypeError, ValueError):
            limit_value = 3

        if limit_value <= 0:
            return []

        params: dict[str, Any] = {
            "docnames": [str(item) for item in seed_docnames],
            "tenant_id": str(tenant_id),
        }

        # CRITICAL: Both seed and related nodes MUST be filtered by tenant_id
        query = f"""
SELECT * FROM ag_catalog.cypher('{self._graph_name}', $$
MATCH (seed:Document)
WHERE seed.docname IN $docnames AND seed.tenant_id = $tenant_id
OPTIONAL MATCH (seed)--(related:Document)
WHERE related.tenant_id = $tenant_id
RETURN seed.docname AS seed_doc,
       related.doctype AS related_type,
       related.docname AS related_doc,
       related.subject AS related_subject
LIMIT {limit_value}
$$, $1::ag_catalog.agtype) AS (
    seed_doc ag_catalog.agtype,
    related_type ag_catalog.agtype,
    related_doc ag_catalog.agtype,
    related_subject ag_catalog.agtype
);
"""

        try:
            rows = await self._execute_cypher(query, params)
        except Exception as exc:
            logger.warning(
                "Graph enrichment failed, falling back to vector-only",
                error=str(exc),
            )
            return []

        enriched: list[dict[str, Any]] = []
        seen: set[str] = set()

        for row in rows:
            seed_doc = _parse_agtype_scalar(row["seed_doc"])
            related_doc = _parse_agtype_scalar(row["related_doc"])

            if related_doc is None:
                continue

            seed_doc_str = "" if seed_doc is None else str(seed_doc)
            related_doc_str = str(related_doc)

            if not related_doc_str or related_doc_str == seed_doc_str:
                continue

            dedupe_key = f"{seed_doc_str}:{related_doc_str}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            related_type = _parse_agtype_scalar(row["related_type"])
            related_subject = _parse_agtype_scalar(row["related_subject"])

            enriched.append(
                {
                    "docname": related_doc_str,
                    "doctype": None if related_type is None else str(related_type),
                    "subject": "N/A" if related_subject is None else str(related_subject),
                    "relationship": f"Linked to {seed_doc_str}",
                }
            )

        return enriched