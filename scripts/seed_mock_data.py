# scripts/seed_mock_data.py
import asyncio
import json
import random
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg
from faker import Faker

from buildpolaris_ai.platform.config import get_settings

fake = Faker()
Faker.seed(42)

_GRAPH_NAME = "polaris_knowledge_graph"
_GRAPH_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROPERTY_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_RESERVED_INPUT_KEYS = {"docname", "doctype", "tenant_id"}
_RESERVED_BUILD_KEYS = {"docname"}


def _validate_identifier(value: str) -> str:
    if not isinstance(value, str) or not _GRAPH_NAME_PATTERN.match(value):
        raise ValueError(f"Unsafe or invalid identifier: {value!r}")
    return value


def _json_safe(value: Any) -> Any:
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
    normalized = _json_safe(value)
    if isinstance(normalized, (dict, list)):
        return json.dumps(normalized, ensure_ascii=False)
    return normalized


def _build_upsert_query(properties: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    graph_name = _validate_identifier(_GRAPH_NAME)
    set_clauses: list[str] = []
    params: dict[str, Any] = {}
    index = 0

    for raw_key, raw_value in properties.items():
        key = str(raw_key)
        if key in _RESERVED_BUILD_KEYS:
            continue
        if not _PROPERTY_KEY_PATTERN.match(key):
            print(f"Warning: skipping unsafe graph property key: {key}")
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
SELECT * FROM ag_catalog.cypher('{graph_name}', $$
MERGE (n:Document {{docname: $docname, tenant_id: $tenant_id}})
SET {set_sql}
RETURN n
$$, $1::ag_catalog.agtype) AS (n ag_catalog.agtype);
"""
    return query, params


async def setup_relational_table(conn: asyncpg.Connection) -> None:
    """Drop and recreate the mock documents table (fully qualified to public)."""
    await conn.execute("DROP TABLE IF EXISTS public.mock_erpnext_docs;")
    await conn.execute(
        """
        CREATE TABLE public.mock_erpnext_docs (
            id UUID PRIMARY KEY,
            tenant_id VARCHAR(100) NOT NULL,
            doctype VARCHAR(50) NOT NULL,
            docname VARCHAR(100) NOT NULL,
            project_id VARCHAR(100) NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    print("Table 'public.mock_erpnext_docs' is recreated and ready.")


async def setup_graph(conn: asyncpg.Connection) -> None:
    """Drop and recreate the AGE graph and set a safe session search_path."""
    await conn.execute("LOAD 'age';")
    # CRITICAL: ag_catalog MUST remain in the search_path for the whole session.
    # AGE's internal agtype operators (e.g. @>) are resolved via search_path;
    # dropping ag_catalog causes "operator does not exist: agtype @> agtype".
    await conn.execute('SET search_path = ag_catalog, "$user", public;')

    graph_name = _validate_identifier(_GRAPH_NAME)
    try:
        await conn.execute(f"SELECT * FROM ag_catalog.drop_graph('{graph_name}', true);")
        print("Dropped existing graph.")
    except Exception:
        pass
    await conn.execute(f"SELECT * FROM ag_catalog.create_graph('{graph_name}');")
    print("Created fresh graph.")


def generate_mock_rfi(project_id: str, index: int) -> tuple[str, dict]:
    docname = f"RFI-{1000 + index}"
    has_cost = fake.boolean(chance_of_getting_true=20)
    has_schedule = fake.boolean(chance_of_getting_true=30)
    payload = {
        "doctype": "RFI",
        "docname": docname,
        "project_id": project_id,
        "subject": fake.sentence(nb_words=6),
        "description": fake.paragraph(nb_sentences=3),
        "raised_by": fake.name(),
        "assigned_to": fake.name(),
        "status": fake.random_element(elements=("Open", "Answered", "Closed")),
        "cost_impact": has_cost,
        "schedule_impact": has_schedule,
        "sla_due": (datetime.now() + timedelta(days=random.randint(1, 7))).isoformat(),
        "created_at": (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat(),
    }
    return docname, payload


def generate_mock_daily_log(project_id: str, index: int) -> tuple[str, dict]:
    docname = f"DLOG-{2000 + index}"
    payload = {
        "doctype": "DailyLog",
        "docname": docname,
        "project_id": project_id,
        "log_date": (datetime.now() - timedelta(days=index)).date().isoformat(),
        "submitted_by": fake.name(),
        "weather": fake.random_element(elements=("Sunny", "Cloudy", "Rainy", "Windy")),
        "labor_hours": random.randint(20, 150),
        "delays": fake.sentence(nb_words=8) if fake.boolean(40) else "None",
        "sync_status": "Synced",
    }
    return docname, payload


def generate_mock_task(project_id: str, index: int) -> tuple[str, dict]:
    docname = f"TASK-{3000 + index}"
    payload = {
        "doctype": "Task",
        "docname": docname,
        "project_id": project_id,
        "title": fake.sentence(nb_words=4),
        "parent_task_id": None,
        "start_date": (datetime.now() - timedelta(days=random.randint(10, 20))).date().isoformat(),
        "end_date": (datetime.now() + timedelta(days=random.randint(1, 15))).date().isoformat(),
        "status": fake.random_element(elements=("Open", "Working", "Completed", "Cancelled")),
    }
    return docname, payload


async def seed_age_graph(
    conn: asyncpg.Connection,
    doctype: str,
    docname: str,
    tenant_id: str,
    payload: dict,
) -> None:
    """Insert a node into the Apache AGE graph using parameterized Cypher."""
    subject = payload.get("subject") or payload.get("title") or "N/A"
    status = payload.get("status") or "N/A"
    project_id = payload.get("project_id") or "N/A"

    clean_input = {"project_id": project_id, "status": status, "subject": subject, "tenant_id": tenant_id}
    clean_properties = {k: v for k, v in clean_input.items() if k not in _RESERVED_INPUT_KEYS}
    merged_properties: dict[str, Any] = {"doctype": doctype, **clean_properties}

    query, property_params = _build_upsert_query(merged_properties)
    params: dict[str, Any] = {"docname": str(docname), "tenant_id": str(tenant_id)}
    params.update(property_params)

    serialized_params = json.dumps(_json_safe(params), ensure_ascii=False)
    try:
        await conn.fetch(query, serialized_params)
    except Exception as e:
        # Fail LOUDLY during seeding so we never silently drop graph data.
        raise RuntimeError(f"AGE graph insert failed for {docname}: {e}") from e


async def main() -> None:
    print("Starting Mock Data Seeder...")
    settings = get_settings()

    conn = await asyncpg.connect(**settings.database.connect_kwargs())
    print("Connected to PostgreSQL.")

    try:
        await setup_relational_table(conn)
        await setup_graph(conn)

        # NOTE: Do NOT reset search_path to public here. ag_catalog must stay
        # visible for the AGE inserts below. Relational tables are fully qualified.

        tenants = ["TENANT-ALPHA", "TENANT-BETA"]
        project_id = "PROJ-ALPHA-001"
        records_to_generate = 15

        doctypes = [
            ("RFI", generate_mock_rfi),
            ("DailyLog", generate_mock_daily_log),
            ("Task", generate_mock_task),
        ]

        for tenant_id in tenants:
            for doctype, generator in doctypes:
                print(f"Generating {records_to_generate} {doctype} records for {tenant_id}...")
                for i in range(records_to_generate):
                    doc_id = str(uuid.uuid4())
                    docname, payload = generator(project_id, i)
                    payload["tenant_id"] = tenant_id

                    created_at_str = payload.get("created_at", datetime.now().isoformat())
                    created_at_dt = datetime.fromisoformat(created_at_str)

                    await conn.execute(
                        "INSERT INTO public.mock_erpnext_docs (id, tenant_id, doctype, docname, project_id, payload, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                        doc_id, tenant_id, doctype, docname, project_id, json.dumps(payload), created_at_dt,
                    )
                    await seed_age_graph(conn, doctype, docname, tenant_id, payload)

                print(f"Successfully seeded {records_to_generate} {doctype} records for {tenant_id}.")

        print("Mock data seeding completed successfully!")
        count = await conn.fetchval("SELECT COUNT(*) FROM public.mock_erpnext_docs")
        print(f"Total records in 'mock_erpnext_docs': {count}")
    finally:
        await conn.close()
        print("Database connection closed.")


if __name__ == "__main__":
    asyncio.run(main())