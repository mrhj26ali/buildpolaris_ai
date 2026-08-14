"""Dev/ops tool â€” replays a captured batch of graph-sync CDC events
against EntityMirrorService, for local testing without a live BFF, or for
recovering from a window where the sidecar was down and missed live
hook-fired events (BFF's own retry/outbox mechanism is the production
answer to that; this script is the manual fallback).

Usage: python scripts/replay_cdc.py path/to/events.jsonl
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.postgres import close_pool, get_pool, init_pool  # noqa: E402
from app.gateway.schemas.graph_sync_event import GraphSyncEvent  # noqa: E402
from app.ingest.entity_mirror_service import EntityMirrorService  # noqa: E402
from app.observability.logging import configure_logging, get_logger  # noqa: E402
from app.platform.graph_store.age_adapter import AgeGraphAdapter  # noqa: E402

configure_logging()
logger = get_logger(__name__)


async def replay(path: Path) -> None:
    await init_pool()
    try:
        async with get_pool().acquire() as conn:
            service = EntityMirrorService(AgeGraphAdapter(conn), conn)

            with path.open(encoding="utf-8") as fh:
                for i, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    event = GraphSyncEvent.model_validate_json(line)
                    result = await service.sync(event)
                    logger.info("event_replayed", line=i, accepted=result.accepted)
    finally:
        await close_pool()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/replay_cdc.py path/to/events.jsonl")
        sys.exit(1)
    asyncio.run(replay(Path(sys.argv[1])))
