"""Seed realistic construction mock data aligned with BuildPolaris MDs."""
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

# Construction-realistic data
CONSTRUCTION_TASKS = [
    ("Site Mobilization", 5), ("Excavation & Grading", 10), ("Foundation Formwork", 7),
    ("Rebar Installation", 5), ("Foundation Concrete Pour", 3), ("Foundation Curing", 7),
    ("Structural Steel Erection", 21), ("Metal Deck Installation", 14),
    ("Concrete Topping Slab", 7), ("Exterior Wall Framing", 14),
    ("MEP Rough-In: Electrical", 21), ("MEP Rough-In: Plumbing", 18),
    ("MEP Rough-In: HVAC", 21), ("Drywall Installation", 14),
    ("Interior Finishes: Paint", 10), ("Flooring Installation", 12),
    ("Roofing Installation", 10), ("Exterior Glazing", 14),
    ("Elevator Installation", 21), ("Fire Protection System", 14),
    ("Landscaping & Site Work", 10), ("Final Cleanup & Punch List", 7),
]

RFI_SUBJECTS = [
    "Concrete mix design discrepancy on foundation pour",
    "HVAC ductwork clearance conflict at Level 2 beam",
    "Structural steel connection detail unclear at grid line C-4",
    "Electrical panel location conflicts with plumbing riser",
    "Roof membrane specification vs. warranty requirements",
    "Fire-rated wall assembly detail at stairwell enclosure",
    "Elevator pit waterproofing detail clarification needed",
    "Window glazing U-value does not match energy code requirement",
    "Rebar spacing conflict at pile cap intersection",
    "Drywall type at rated corridor not matching spec section",
    "Plumbing vent stack penetration through fire-rated floor",
    "Steel beam camber requirement for long-span area",
    "Curtain wall anchor detail at slab edge condition",
    "Mechanical room equipment clearance for maintenance access",
    "Parking garage drainage slope conflicts with column layout",
]

DAILY_LOG_NOTES = [
    "Crew of 12 installed rebar for foundation wall section B. No delays.",
    "Concrete pour for slab on grade, zones 1-3 completed. Weather cooperative.",
    "Steel erection progressed on east side. Crane operational all day.",
    "MEP coordination meeting held. Resolved duct conflict at Level 2.",
    "Drywall crew started Level 1 corridors. Material delivery on schedule.",
    "Roofing membrane installation 60% complete. Wind delays in afternoon.",
    "Electrical rough-in continuing on Level 3. Inspector visit scheduled.",
    "Excavation for utility trench completed. Shoring inspected and approved.",
    "Plumbing riser installation Level 2. Pressure test scheduled tomorrow.",
    "Paint crew mobilized for interior offices. Color samples approved.",
    "Elevator guide rail installation started. Hoistway verified plumb.",
    "Fire sprinkler main installation in basement. Hydro test pending.",
    "Landscaping crew graded south side. Topsoil delivery received.",
    "Punch list walkthrough with architect on Level 1. 15 items noted.",
    "Weather delay - rain. Interior work continued. No exterior operations.",
]

PUNCH_ITEMS = [
    "Drywall finish defects in corridor Level 1 require rework before paint",
    "Paint touch-up needed at door frames Level 2 east wing",
    "Missing ceiling tile in conference room 301",
    "Door hardware adjustment needed at stairwell B Level 1",
    "Caulking incomplete at window perimeters Level 3 north",
    "HVAC diffuser alignment correction in office 205",
    "Electrical outlet cover plates missing in mechanical room",
    "Flooring transition strip loose at corridor junction Level 1",
    "Plumbing fixture alignment at restroom Level 2",
    "Fire extinguisher cabinet door latch repair Level 1",
]


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
    return str(value)


def generate_tasks(project_id: str, tenant_id: str) -> list[dict]:
    records = []
    start_date = datetime.now() - timedelta(days=60)
    for i, (title, duration) in enumerate(CONSTRUCTION_TASKS):
        docname = f"TASK-{3000 + i}"
        task_start = start_date + timedelta(days=sum(d for _, d in CONSTRUCTION_TASKS[:i]) // 2)
        task_end = task_start + timedelta(days=duration)
        records.append({
            "doctype": "Task", "docname": docname, "tenant_id": tenant_id,
            "project_id": project_id, "task_id": docname,
            "title": title,
            "start_date": task_start.date().isoformat(),
            "end_date": task_end.date().isoformat(),
            "duration": duration,
            "total_float": round(random.uniform(0, 5), 2),
            "is_critical": i < 6,  # First tasks are critical path
            "status": random.choice(["Working", "Completed", "Open"]),
            "description": f"{title}: {duration}-day activity for {project_id}.",
            "created_at": datetime.now().isoformat(),
        })
    return records


def generate_rfis(project_id: str, tenant_id: str) -> list[dict]:
    records = []
    for i, subject in enumerate(RFI_SUBJECTS):
        docname = f"RFI-{1000 + i}"
        records.append({
            "doctype": "RFI", "docname": docname, "tenant_id": tenant_id,
            "project_id": project_id, "rfi_id": docname,
            "raised_by": fake.name(), "assigned_to": fake.name(),
            "status": random.choice(["Draft", "Open", "Answered", "Closed"]),
            "cost_impact": random.random() < 0.3,
            "schedule_impact": random.random() < 0.4,
            "sla_due": (datetime.now() + timedelta(days=random.randint(1, 7))).isoformat(),
            "subject": subject,
            "description": f"RFI regarding {subject.lower()}. Requires clarification from design team.",
            "created_at": (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat(),
        })
    return records


def generate_daily_logs(project_id: str, tenant_id: str) -> list[dict]:
    records = []
    for i, note in enumerate(DAILY_LOG_NOTES):
        docname = f"DLOG-{2000 + i}"
        records.append({
            "doctype": "DailyLog", "docname": docname, "tenant_id": tenant_id,
            "project_id": project_id, "log_id": docname,
            "submitted_by": fake.name(),
            "log_date": (datetime.now() - timedelta(days=i)).date().isoformat(),
            "weather": random.choice(["Sunny", "Cloudy", "Rainy", "Windy", "Clear"]),
            "labor_hours": random.randint(40, 160),
            "delays": "Weather delay" if "rain" in note.lower() else "None",
            "sync_status": "Synced",
            "source": random.choice(["manual", "automated", "automated_confirmed"]),
            "capture_confidence": round(random.uniform(0.7, 1.0), 3),
            "description": note,
            "created_at": datetime.now().isoformat(),
        })
    return records


def generate_punch_items(project_id: str, tenant_id: str) -> list[dict]:
    records = []
    for i, desc in enumerate(PUNCH_ITEMS):
        docname = f"PLI-{7000 + i}"
        records.append({
            "doctype": "PunchListItem", "docname": docname, "tenant_id": tenant_id,
            "project_id": project_id, "punch_id": docname,
            "drawing_revision_id": f"DWG-REV-{random.randint(1, 5)}",
            "assigned_to": random.choice(["Drywall Sub", "Paint Sub", "MEP Sub", "GC"]),
            "due_date": (datetime.now() + timedelta(days=random.randint(1, 14))).date().isoformat(),
            "status": random.choice(["Open", "PendingVerification", "Closed"]),
            "geo_lat": round(fake.latitude(), 6),
            "geo_long": round(fake.longitude(), 6),
            "source": "manual",
            "capture_confidence": 1.0,
            "description": desc,
            "created_at": datetime.now().isoformat(),
        })
    return records


def generate_change_events(project_id: str, tenant_id: str, rfis: list[dict]) -> list[dict]:
    records = []
    categories = ("scope-gap", "design-error", "field-condition", "owner-request", "other")
    for i in range(8):
        docname = f"CE-{5000 + i}"
        source = random.choice(rfis) if rfis else None
        records.append({
            "doctype": "ChangeEvent", "docname": docname, "tenant_id": tenant_id,
            "project_id": project_id, "event_id": docname,
            "source_doctype": "RFI" if source else "FieldIssue",
            "source_id": source["docname"] if source else f"FIELD-{6000 + i}",
            "category": random.choice(categories),
            "potential_cost_impact": round(random.uniform(500, 50000), 2),
            "potential_schedule_impact_days": random.randint(0, 21),
            "status": random.choice(["Potential", "Validated", "Dismissed"]),
            "outcome_reason": f"Change identified from {source['subject'] if source else 'field condition'}.",
            "description": f"Change event {docname}: potential cost/schedule impact identified.",
            "created_at": datetime.now().isoformat(),
        })
    return records


def generate_all_for_tenant(project_id: str, tenant_id: str) -> tuple[list[dict], list[tuple]]:
    tasks = generate_tasks(project_id, tenant_id)
    rfis = generate_rfis(project_id, tenant_id)
    daily_logs = generate_daily_logs(project_id, tenant_id)
    punch_items = generate_punch_items(project_id, tenant_id)
    change_events = generate_change_events(project_id, tenant_id, rfis)

    all_records = tasks + rfis + daily_logs + punch_items + change_events

    # Derive graph edges
    edges = []
    for ce in change_events:
        if ce["source_doctype"] == "RFI":
            edges.append((ce["docname"], ce["source_id"], "SOURCED_FROM"))

    return all_records, edges


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
    print("Table 'mock_erpnext_docs' recreated.")


async def setup_graph(conn: asyncpg.Connection) -> None:
    await conn.execute("LOAD 'age';")
    await conn.execute('SET search_path = ag_catalog, "$user", public;')
    try:
        await conn.execute(f"SELECT * FROM ag_catalog.drop_graph('{_GRAPH_NAME}', true);")
    except Exception:
        pass
    await conn.execute(f"SELECT * FROM ag_catalog.create_graph('{_GRAPH_NAME}');")
    print("Graph recreated.")


async def insert_relational(conn, records: list[dict]) -> None:
    for payload in records:
        await conn.execute(
            "INSERT INTO public.mock_erpnext_docs (id, tenant_id, doctype, docname, project_id, payload, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            str(uuid.uuid4()), payload["tenant_id"], payload["doctype"], payload["docname"],
            payload["project_id"], json.dumps(payload, default=str), datetime.now(),
        )


async def seed_age_node(conn, payload: dict) -> None:
    properties = {
        "project_id": payload.get("project_id", "N/A"),
        "status": payload.get("status", "N/A"),
        "subject": payload.get("subject") or payload.get("title") or payload.get("description", "N/A"),
        "tenant_id": payload["tenant_id"],
        "doctype": payload["doctype"],
    }
    params = {"docname": payload["docname"], **properties}
    set_clauses = ", ".join(f"n.{k} = ${k}" for k in properties.keys() if k != "docname")
    query = f"""
        SELECT * FROM ag_catalog.cypher('{_GRAPH_NAME}', $$
            MERGE (n:Document {{docname: $docname, tenant_id: $tenant_id}})
            SET {set_clauses}
            RETURN n
        $$, $1::ag_catalog.agtype) AS (n ag_catalog.agtype);
    """
    await conn.fetch(query, json.dumps(_json_safe(params), ensure_ascii=False))


async def seed_age_edge(conn, from_dn: str, to_dn: str, rel_type: str, tenant_id: str) -> None:
    query = f"""
        SELECT * FROM ag_catalog.cypher('{_GRAPH_NAME}', $$
            MATCH (a:Document {{docname: $from_dn, tenant_id: $tenant_id}}),
                  (b:Document {{docname: $to_dn, tenant_id: $tenant_id}})
            CREATE (a)-[:{rel_type}]->(b)
        $$, $1::ag_catalog.agtype) AS (result ag_catalog.agtype);
    """
    params = {"from_dn": from_dn, "to_dn": to_dn, "tenant_id": tenant_id}
    await conn.fetch(query, json.dumps(_json_safe(params), ensure_ascii=False))


async def main() -> None:
    print("Starting Mock Data Seeder (Construction-Realistic)...")
    settings = get_settings()
    conn = await asyncpg.connect(**settings.database.connect_kwargs())
    print("Connected to PostgreSQL.")

    try:
        await setup_relational_table(conn)
        await setup_graph(conn)

        tenants = ["TENANT-ALPHA", "TENANT-BETA"]
        project_id = "PROJ-ALPHA-001"

        for tenant_id in tenants:
            records, edges = generate_all_for_tenant(project_id, tenant_id)
            await insert_relational(conn, records)
            for payload in records:
                await seed_age_node(conn, payload)
            for from_dn, to_dn, rel_type in edges:
                await seed_age_edge(conn, from_dn, to_dn, rel_type, tenant_id)
            print(f"Seeded {len(records)} records + {len(edges)} edges for {tenant_id}.")

        count = await conn.fetchval("SELECT COUNT(*) FROM public.mock_erpnext_docs")
        print(f"Total records: {count}")
        print("Mock data seeding completed!")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
