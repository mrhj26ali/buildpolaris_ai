"""Row model for `approval_events` (migration 0007) â€” mirrors what this
sidecar proposed to the BFF's ActionApprovalGate, for its own audit trail
(ActionApprovalGateClient never resolves an approval, only proposes it)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class ApprovalEvent:
    event_id: UUID
    run_id: UUID | None
    tool_trace_id: str
    proposed_payload: dict
    bff_approval_ref: str | None
    proposed_at: datetime
    idempotency_key: str

    @classmethod
    def from_record(cls, record: Any) -> "ApprovalEvent":
        return cls(**dict(record))
