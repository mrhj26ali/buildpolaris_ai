"""Rebuilds this sidecar's ENTIRE derived store (document_chunks,
embeddings, graph_node_index, graph_edge_index, AND the AGE graph itself)
from scratch. This is the operational proof of ERD Â§1's core promise:
"MariaDB is the only place a fact is created. RxDB and the AI sidecar's
Postgres are both disposable projections that can be deleted and
rebuilt."

This script does NOT re-fetch every source document from BFF itself â€” it
drops the derived tables, re-runs migrations, and then expects the
operator (or a companion BFF-side script) to re-trigger ingestion/graph-
sync for every eligible document and tracked entity. What it guarantees
is that starting state is clean and idempotent re-ingestion will not
collide with stale rows.

Usage: python scripts/rebuild_read_model.py --confirm
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.observability.logging import configure_logging, get_logger  # noqa: E402

configure_logging()
logger = get_logger(__name__)

TABLES_TO_TRUNCATE = [
    "embeddings", "document_chunks", "graph_edge_index", "graph_node_index",
    "graph_sync_cursor", "agent_runs", "approval_events",
]


async def rebuild() -> None:
    import asyncpg

    settings = get_settings().database
    conn = await asyncpg.connect(**settings.connect_kwargs())
    try:
        for table in TABLES_TO_TRUNCATE:
            await conn.execute(f"TRUNCATE TABLE {table} CASCADE;")
            logger.info("table_truncated", table=table)

        await conn.execute("LOAD 'age'; SET search_path = ag_catalog, \"$user\", public;")
        await conn.execute(
            "SELECT drop_graph('buildpolaris_graph', true) "
            "WHERE EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'buildpolaris_graph');"
        )
        await conn.execute("SELECT create_graph('buildpolaris_graph');")
        logger.info("age_graph_recreated")
    finally:
        await conn.close()

    print(
        "Derived store truncated and AGE graph recreated. Now trigger "
        "re-ingestion/graph-sync from buildpolaris_bff for every eligible "
        "document and tracked entity."
    )


if __name__ == "__main__":
    if "--confirm" not in sys.argv:
        print("This TRUNCATEs every derived table and drops the AGE graph. "
              "Re-run with --confirm to proceed.")
        sys.exit(1)
    asyncio.run(rebuild())
