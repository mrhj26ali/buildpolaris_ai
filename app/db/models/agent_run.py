"""Row model for `agent_runs` (migration 0007) â€” sidecar-local run
tracking, feeding eval/metrics/*.py. NOT the approval authority (that's
MariaDB's Agent Action Approval, ERD Â§3.6)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class AgentRun:
    run_id: UUID
    agent_type: str
    company: str
    project: str | None
    user_id: str
    trace_id: str
    model_version: str
    confidence: Decimal | None
    output_kind: str  # 'read_only' | 'proposed_write'
    started_at: datetime
    completed_at: datetime | None
    status: str  # 'running' | 'succeeded' | 'failed'

    @classmethod
    def from_record(cls, record: Any) -> "AgentRun":
        return cls(**dict(record))
