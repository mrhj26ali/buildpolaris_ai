"""Sidecar-local audit trail for every proposal this service makes,
independent of whatever the BFF later records â€” so buildpolaris_ai's own
eval/metrics (approval_gate_accuracy.py) never depends on being able to
query MariaDB (ERD Â§7 / migration 0007's approval_events table).
"""
from __future__ import annotations

import asyncpg

from app.observability.logging import get_logger
from app.platform.governance.proposal_schema import ProposedAction

logger = get_logger(__name__)


async def record_approval_event(
    conn: asyncpg.Connection, run_id: str | None, action: ProposedAction,
    bff_approval_ref: str | None,
) -> None:
    import json

    await conn.execute(
        """
        INSERT INTO approval_events
            (run_id, tool_trace_id, proposed_payload, bff_approval_ref, idempotency_key)
        VALUES ($1, $2, $3::jsonb, $4, $5)
        ON CONFLICT (idempotency_key) DO UPDATE
            SET bff_approval_ref = EXCLUDED.bff_approval_ref;
        """,
        run_id, action.tool_trace_id, json.dumps(action.payload), bff_approval_ref,
        action.idempotency_key,
    )
    logger.info(
        "approval_event_recorded",
        agent_type=action.agent_type, tool_trace_id=action.tool_trace_id,
        bff_approval_ref=bff_approval_ref,
    )
