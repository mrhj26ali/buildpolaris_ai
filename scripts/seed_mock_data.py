# scripts/seed_mock_data.py
"""
Phase 1 — Mock Data ERD Expansion.
Expands the mock dataset to cover the full entity set the AI layer touches,
matching construction_pm_platform_spec_FINAL.md Section 9 ERDs field-for-field:
RFI, Task, DailyLog, PunchListItem, ChangeEvent, ContractClause,
ScheduleOfValuesLine (SOV/Budget), IncidentReport (Safety), ActionApprovalGate.

Each record also carries a `description` field as a deliberate mock enrichment
so the downstream embedding pipeline (graph_sync_worker) has meaningful text to
embed. Domain fields follow the spec ERDs exactly.

Knowledge-graph edges are created from real cross-references:
ChangeEvent -[:SOURCED_FROM]-> RFI
ScheduleOfValuesLine -[:MAPS_TO_TASK]-> Task
Edges are tenant-scoped so the graph never leaks across tenants (NFR-AI-3).
"""
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
random.seed(42)

_GRAPH_NAME = "polaris_knowledge_graph"
_GRAPH_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROPERTY_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REL_TYPE_WHITELIST = {"SOURCED_FROM", "MAPS_TO_TASK", "REFERENCES"}
_RESERVED_INPUT_KEYS = {"docname", "doctype", "tenant_id"}
_RESERVED_BUILD_KEYS = {"docname"}

COUNTS = {
    "Task": 10,
    "ScheduleOfValuesLine": 10,
    "RFI": 15,
    "ChangeEvent": 8,
    "DailyLog": 15,
    "PunchListItem": 10,
    "IncidentReport": 5,
    "ContractClause": 6,
    "ActionApprovalGate": 5,
}


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
    """Build a parameterized AGE node upsert (tenant-scoped MERGE)."""
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


def _iso_date(d: date) -> str:
    return d.isoformat()


# ---------------------------------------------------------------------------
# Schema setup
# ---------------------------------------------------------------------------
async def setup_relational_table(conn: asyncpg.Connection) -> None:
    await conn.execute("DROP TABLE IF EXISTS public.mock_erpnext_docs;")
    await conn.execute("""
        CREATE TABLE public.mock_erpnext_docs (
            id UUID PRIMARY KEY,
            tenant_id VARCHAR(100) NOT NULL,
            doctype VARCHAR(50) NOT NULL,
            docname VARCHAR(100) NOT NULL,
            project_id VARCHAR(100) NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    print("Table 'public.mock_erpnext_docs' is recreated and ready.")


async def setup_graph(conn: asyncpg.Connection) -> None:
    await conn.execute("LOAD 'age';")
    await conn.execute('SET search_path = ag_catalog, "$user", public;')
    graph_name = _validate_identifier(_GRAPH_NAME)
    try:
        await conn.execute(f"SELECT * FROM ag_catalog.drop_graph('{graph_name}', true);")
        print("Dropped existing graph.")
    except Exception:
        pass
    await conn.execute(f"SELECT * FROM ag_catalog.create_graph('{graph_name}');")
    print("Created fresh graph.")


# ---------------------------------------------------------------------------
# Generators — one per doctype, field-for-field vs spec Section 9
# ---------------------------------------------------------------------------
def generate_tasks(project_id: str, tenant_id: str, count: int) -> list[dict]:
    records = []
    for i in range(count):
        docname = f"TASK-{3000 + i}"
        start = datetime.now() - timedelta(days=random.randint(10, 30))
        end = start + timedelta(days=random.randint(1, 20))
        records.append({
            "doctype": "Task",
            "docname": docname,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "task_id": docname,
            "parent_task_id": None,
            "title": fake.sentence(nb_words=4),
            "start_date": _iso_date(start.date()),
            "end_date": _iso_date(end.date()),
            "duration": (end - start).days,
            "total_float": round(random.uniform(0, 5), 2),
            "is_critical": fake.boolean(chance_of_getting_true=30),
            "status": fake.random_element(elements=("Open", "Working", "Completed", "Cancelled")),
            "description": f"Task {docname}: {fake.sentence(nb_words=8)}",
            "created_at": (datetime.now() - timedelta(days=random.randint(1, 40))).isoformat(),
        })
    return records


def generate_sov_lines(project_id: str, tenant_id: str, tasks: list[dict]) -> list[dict]:
    records = []
    for i, task in enumerate(tasks):
        docname = f"SOV-{4000 + i}"
        original = round(random.uniform(10_000, 250_000), 2)
        records.append({
            "doctype": "SOVLine",
            "docname": docname,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "sov_line_id": docname,
            "task_id": task["docname"],
            "original_estimate": original,
            "approved_budget": original,
            "committed_cost": round(original * random.uniform(0.3, 0.9), 2),
            "revised_budget": original,
            "description": f"SOV line {docname} mapped to {task['docname']}: {fake.sentence(nb_words=6)}",
            "created_at": datetime.now().isoformat(),
        })
    return records


def generate_rfis(project_id: str, tenant_id: str, count: int) -> list[dict]:
    records = []
    for i in range(count):
        docname = f"RFI-{1000 + i}"
        records.append({
            "doctype": "RFI",
            "docname": docname,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "rfi_id": docname,
            "raised_by": fake.name(),
            "assigned_to": fake.name(),
            "status": fake.random_element(elements=("Draft", "Open", "Answered", "Closed")),
            "cost_impact": fake.boolean(chance_of_getting_true=20),
            "schedule_impact": fake.boolean(chance_of_getting_true=30),
            "sla_due": (datetime.now() + timedelta(days=random.randint(1, 7))).isoformat(),
            "subject": fake.sentence(nb_words=6),
            "description": fake.paragraph(nb_sentences=3),
            "created_at": (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat(),
        })
    return records


def generate_change_events(project_id: str, tenant_id: str, rfis: list[dict], count: int) -> list[dict]:
    records = []
    categories = ("scope-gap", "design-error", "field-condition", "owner-request", "other")
    for i in range(count):
        docname = f"CE-{5000 + i}"
        if rfis and random.random() < 0.7:
            source = random.choice(rfis)
            source_doctype, source_id = "RFI", source["docname"]
        else:
            source_doctype, source_id = "FieldIssue", f"FIELD-{6000 + i}"
        records.append({
            "doctype": "ChangeEvent",
            "docname": docname,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "event_id": docname,
            "source_doctype": source_doctype,
            "source_id": source_id,
            "category": random.choice(categories),
            "potential_cost_impact": round(random.uniform(500, 50_000), 2),
            "potential_schedule_impact_days": random.randint(0, 21),
            "status": fake.random_element(elements=("Potential", "Validated", "Dismissed")),
            "outcome_reason": fake.sentence(nb_words=10),
            "description": f"Change event {docname}: {fake.sentence(nb_words=8)}",
            "created_at": datetime.now().isoformat(),
        })
    return records


def generate_daily_logs(project_id: str, tenant_id: str, count: int) -> list[dict]:
    records = []
    for i in range(count):
        docname = f"DLOG-{2000 + i}"
        records.append({
            "doctype": "DailyLog",
            "docname": docname,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "log_id": docname,
            "submitted_by": fake.name(),
            "log_date": _iso_date((datetime.now() - timedelta(days=i)).date()),
            "weather": fake.random_element(elements=("Sunny", "Cloudy", "Rainy", "Windy")),
            "labor_hours": random.randint(20, 150),
            "delays": fake.sentence(nb_words=8) if fake.boolean(40) else "None",
            "sync_status": "Synced",
            "source": fake.random_element(elements=("manual", "automated", "automated_confirmed")),
            "capture_confidence": round(random.uniform(0.7, 1.0), 3),
            "description": f"Daily log {docname}: {fake.sentence(nb_words=8)}",
            "created_at": datetime.now().isoformat(),
        })
    return records


def generate_punch_items(project_id: str, tenant_id: str, count: int) -> list[dict]:
    records = []
    for i in range(count):
        docname = f"PLI-{7000 + i}"
        records.append({
            "doctype": "PunchListItem",
            "docname": docname,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "punch_id": docname,
            "drawing_revision_id": f"DWG-REV-{random.randint(1, 5)}",
            "assigned_to": fake.name(),
            "due_date": _iso_date((datetime.now() + timedelta(days=random.randint(1, 14))).date()),
            "status": fake.random_element(elements=("Open", "PendingVerification", "Closed")),
            "geo_lat": round(fake.latitude(), 6),
            "geo_long": round(fake.longitude(), 6),
            "source": fake.random_element(elements=("manual", "automated", "automated_confirmed")),
            "capture_confidence": round(random.uniform(0.7, 1.0), 3),
            "description": f"Punch item {docname}: {fake.sentence(nb_words=8)}",
            "created_at": datetime.now().isoformat(),
        })
    return records


def generate_incident_reports(project_id: str, tenant_id: str, count: int) -> list[dict]:
    records = []
    osha_classes = ("Fall", "Struck-By", "Electrical", "Caught-In/Between", "Other")
    for i in range(count):
        docname = f"IR-{8000 + i}"
        records.append({
            "doctype": "IncidentReport",
            "docname": docname,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "incident_id": docname,
            "reported_by": fake.name(),
            "occurred_at": (datetime.now() - timedelta(days=random.randint(1, 60))).isoformat(),
            "osha_classification": random.choice(osha_classes),
            "description": fake.paragraph(nb_sentences=2),
            "created_at": datetime.now().isoformat(),
        })
    return records


def generate_contract_clauses(project_id: str, tenant_id: str, count: int) -> list[dict]:
    records = []
    clause_types = ("indemnification", "liability", "termination", "other")
    risk_flags = ("None", "Low", "Medium", "High")
    for i in range(count):
        docname = f"CLAUSE-{9000 + i}"
        ctype = random.choice(clause_types)
        records.append({
            "doctype": "ContractClause",
            "docname": docname,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "clause_id": docname,
            "source_file_id": f"CONTRACT-DOC-{random.randint(1, 3)}",
            "clause_type": ctype,
            "extracted_text": fake.paragraph(nb_sentences=3),
            "risk_flag": random.choice(risk_flags),
            "review_status": fake.random_element(elements=("Pending", "Reviewed", "Dismissed")),
            "reviewed_by": fake.name() if fake.boolean(60) else None,
            "linked_change_event_id": None,
            "description": f"Contract clause {docname} ({ctype}): {fake.sentence(nb_words=6)}",
            "created_at": datetime.now().isoformat(),
        })
    return records


def generate_approval_gates(project_id: str, tenant_id: str, count: int) -> list[dict]:
    records = []
    for i in range(count):
        docname = f"GATE-{10000 + i}"
        decided = fake.boolean(70)
        records.append({
            "doctype": "ActionApprovalGate",
            "docname": docname,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "gate_id": docname,
            "ref_doctype": random.choice(("RFI", "Task", "ChangeEvent")),
            "ref_docname": f"REF-{random.randint(1000, 9999)}",
            "initiator_type": random.choice(("user", "system")),
            "proposed_payload": {"field": "status", "value": "Approved"},
            "status": fake.random_element(elements=("Pending", "Approved", "Rejected")),
            "approver_id": fake.name() if decided else None,
            "decided_at": datetime.now().isoformat() if decided else None,
            "source_version": "v1.0",
            "confidence_score": round(random.uniform(0.6, 0.99), 3),
            "trace_id": str(uuid.uuid4()),
            "description": f"Approval gate {docname}: {fake.sentence(nb_words=8)}",
            "created_at": datetime.now().isoformat(),
        })
    return records


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def generate_all_for_tenant(project_id: str, tenant_id: str) -> tuple[list[dict], list[tuple]]:
    """Generate every doctype for one tenant; derive knowledge-graph edges."""
    tasks = generate_tasks(project_id, tenant_id, COUNTS["Task"])
    sov_lines = generate_sov_lines(project_id, tenant_id, tasks)
    rfis = generate_rfis(project_id, tenant_id, COUNTS["RFI"])
    change_events = generate_change_events(project_id, tenant_id, rfis, COUNTS["ChangeEvent"])
    daily_logs = generate_daily_logs(project_id, tenant_id, COUNTS["DailyLog"])
    punch_items = generate_punch_items(project_id, tenant_id, COUNTS["PunchListItem"])
    incidents = generate_incident_reports(project_id, tenant_id, COUNTS["IncidentReport"])
    clauses = generate_contract_clauses(project_id, tenant_id, COUNTS["ContractClause"])
    gates = generate_approval_gates(project_id, tenant_id, COUNTS["ActionApprovalGate"])

    all_records = (
        tasks + sov_lines + rfis + change_events + daily_logs
        + punch_items + incidents + clauses + gates
    )

    edges: list[tuple] = []
    for ce in change_events:
        if ce["source_doctype"] == "RFI":
            edges.append((ce["docname"], ce["source_id"], "SOURCED_FROM"))
    for sov in sov_lines:
        edges.append((sov["docname"], sov["task_id"], "MAPS_TO_TASK"))

    return all_records, edges


async def insert_relational(conn: asyncpg.Connection, records: list[dict]) -> None:
    for payload in records:
        doc_id = str(uuid.uuid4())
        created_at_str = payload.get("created_at", datetime.now().isoformat())
        created_at_dt = datetime.fromisoformat(created_at_str)
        await conn.execute(
            "INSERT INTO public.mock_erpnext_docs "
            "(id, tenant_id, doctype, docname, project_id, payload, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            doc_id,
            payload["tenant_id"],
            payload["doctype"],
            payload["docname"],
            payload["project_id"],
            json.dumps(payload, default=str),
            created_at_dt,
        )


async def seed_age_node(conn: asyncpg.Connection, payload: dict) -> None:
    """Create/update a tenant-scoped Document node for one record."""
    properties = {
        "project_id": payload.get("project_id", "N/A"),
        "status": payload.get("status", "N/A"),
        "subject": payload.get("subject") or payload.get("title") or payload.get("description", "N/A"),
        "tenant_id": payload["tenant_id"],
    }
    clean_properties = {k: v for k, v in properties.items() if k not in _RESERVED_INPUT_KEYS}
    merged_properties: dict[str, Any] = {"doctype": payload["doctype"], **clean_properties}
    query, property_params = _build_upsert_query(merged_properties)
    params: dict[str, Any] = {"docname": payload["docname"], "tenant_id": payload["tenant_id"]}
    params.update(property_params)
    serialized_params = json.dumps(_json_safe(params), ensure_ascii=False)
    try:
        await conn.fetch(query, serialized_params)
    except Exception as e:
        raise RuntimeError(f"AGE node insert failed for {payload['docname']}: {e}") from e


async def seed_age_edge(
    conn: asyncpg.Connection,
    from_docname: str,
    to_docname: str,
    rel_type: str,
    tenant_id: str,
) -> None:
    """Create a tenant-scoped edge between two Document nodes (parameterized)."""
    if rel_type not in _REL_TYPE_WHITELIST:
        raise ValueError(f"Disallowed relationship type: {rel_type!r}")
    graph_name = _validate_identifier(_GRAPH_NAME)
    query = f"""
SELECT * FROM ag_catalog.cypher('{graph_name}', $$
MATCH (a:Document {{docname: $from_dn, tenant_id: $tenant_id}}),
(b:Document {{docname: $to_dn, tenant_id: $tenant_id}})
CREATE (a)-[:{rel_type}]->(b)
$$, $1::ag_catalog.agtype) AS (result ag_catalog.agtype);
"""
    params = {"from_dn": from_docname, "to_dn": to_docname, "tenant_id": tenant_id}
    try:
        await conn.fetch(query, json.dumps(_json_safe(params), ensure_ascii=False))
    except Exception as e:
        raise RuntimeError(f"AGE edge insert failed {from_docname}->{to_docname}: {e}") from e


async def main() -> None:
    print("Starting Mock Data Seeder (Phase 1 — ERD expansion)...")
    settings = get_settings()
    conn = await asyncpg.connect(**settings.database.connect_kwargs())
    print("Connected to PostgreSQL.")

    try:
        await setup_relational_table(conn)
        await setup_graph(conn)

        tenants = ["TENANT-ALPHA", "TENANT-BETA"]
        project_id = "PROJ-ALPHA-001"
        total_records = 0
        total_edges = 0

        for tenant_id in tenants:
            records, edges = generate_all_for_tenant(project_id, tenant_id)
            await insert_relational(conn, records)
            for payload in records:
                await seed_age_node(conn, payload)
            for from_dn, to_dn, rel_type in edges:
                await seed_age_edge(conn, from_dn, to_dn, rel_type, tenant_id)
            total_records += len(records)
            total_edges += len(edges)
            print(f"Seeded {len(records)} records + {len(edges)} edges for {tenant_id}.")

        count = await conn.fetchval("SELECT COUNT(*) FROM public.mock_erpnext_docs")
        print("Mock data seeding completed successfully!")
        print(f"Total records in 'mock_erpnext_docs': {count}")
        print(f"Total knowledge-graph edges created: {total_edges}")
    finally:
        await conn.close()
        print("Database connection closed.")


if __name__ == "__main__":
    asyncio.run(main())
