# scripts/seed_mock_data.py
import asyncio
import asyncpg
import json
import random
from datetime import datetime, timedelta
from faker import Faker
import uuid
import os

# Initialize Faker with a seed for reproducible mock data
fake = Faker()
Faker.seed(42)

# Database connection parameters (matching docker-compose.yml)
DB_USER = os.getenv("DB_USER", "polaris_ai")
DB_PASSWORD = os.getenv("DB_PASSWORD", "polaris_ai_dev_password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "polaris_knowledge")

async def setup_relational_table(conn):
    """Create the mock documents table if it doesn't exist and clear it."""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS mock_erpnext_docs (
            id UUID PRIMARY KEY,
            doctype VARCHAR(50) NOT NULL,
            docname VARCHAR(100) NOT NULL,
            project_id VARCHAR(100) NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Clear existing data to ensure a clean slate
    await conn.execute("TRUNCATE TABLE mock_erpnext_docs;")
    print("✅ Table 'mock_erpnext_docs' is ready and cleared.")

async def setup_graph(conn):
    """Drop and recreate the Apache AGE graph to ensure a clean slate."""
    try:
        # Fully qualify the drop_graph function
        await conn.execute("SELECT * FROM ag_catalog.drop_graph('polaris_knowledge_graph', true);")
        print("🗑️ Dropped existing graph 'polaris_knowledge_graph'.")
    except Exception:
        # If it doesn't exist, it throws an error, which is fine.
        pass
    
    # Fully qualify the create_graph function
    await conn.execute("SELECT * FROM ag_catalog.create_graph('polaris_knowledge_graph');")
    print("✅ Created fresh graph 'polaris_knowledge_graph'.")

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
        "created_at": (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat()
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
        "sync_status": "Synced"
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
        "status": fake.random_element(elements=("Open", "Working", "Completed", "Cancelled"))
    }
    return docname, payload

async def seed_age_graph(conn, doctype: str, docname: str, payload: dict):
    """Insert a node into the Apache AGE graph."""
    subject = payload.get("subject") or payload.get("title") or "N/A"
    status = payload.get("status") or "N/A"
    project_id = payload.get("project_id")
    
    # Basic sanitization for Cypher injection (sufficient for local mock data)
    safe_subject = str(subject).replace("'", "''")
    safe_docname = str(docname).replace("'", "''")
    
    # Fully qualify cypher and agtype to completely avoid search_path issues
    query = f"""
        SELECT * FROM ag_catalog.cypher('polaris_knowledge_graph', $$
            CREATE (n:Document {{
                doctype: '{doctype}',
                docname: '{safe_docname}',
                project_id: '{project_id}',
                subject: '{safe_subject}',
                status: '{status}'
            }})
            RETURN n
        $$) AS (n ag_catalog.agtype);
    """
    try:
        await conn.execute(query)
    except Exception as e:
        print(f"⚠️ Warning: Could not insert into AGE graph for {docname}. Error: {e}")

async def main():
    print("🚀 Starting Mock Data Seeder...")
    
    # Connect to the database
    conn = await asyncpg.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME
    )
    print("✅ Connected to PostgreSQL.")

    try:
        # 1. Setup Relational Table
        await setup_relational_table(conn)
        
        # 2. Setup Graph (Drop and Recreate for a clean slate)
        await setup_graph(conn)
        
        project_id = "PROJ-ALPHA-001"
        records_to_generate = 15 # Per doctype
        
        doctypes = [
            ("RFI", generate_mock_rfi),
            ("DailyLog", generate_mock_daily_log),
            ("Task", generate_mock_task)
        ]
        
        for doctype, generator in doctypes:
            print(f"\n📦 Generating {records_to_generate} {doctype} records...")
            for i in range(records_to_generate):
                doc_id = str(uuid.uuid4())
                docname, payload = generator(project_id, i)
                
                # 1. Insert into relational table
                created_at_str = payload.get("created_at", datetime.now().isoformat())
                created_at_dt = datetime.fromisoformat(created_at_str)
                
                await conn.execute("""
                    INSERT INTO mock_erpnext_docs (id, doctype, docname, project_id, payload, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, doc_id, doctype, docname, project_id, json.dumps(payload), created_at_dt)
                
                # 2. Insert into Apache AGE graph
                await seed_age_graph(conn, doctype, docname, payload)
                
            print(f"✅ Successfully seeded {records_to_generate} {doctype} records.")

        print("\n🎉 Mock data seeding completed successfully!")
        
        # Verification query
        count = await conn.fetchval("SELECT COUNT(*) FROM mock_erpnext_docs")
        print(f"📊 Total records in 'mock_erpnext_docs': {count}")
        
    finally:
        await conn.close()
        print("🔌 Database connection closed.")

if __name__ == "__main__":
    asyncio.run(main())