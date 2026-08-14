"""ProposedAction â€” what an agent hands to ActionApprovalGateClient
(ARCH Flowchart 4 step O: "capture agent type, payload, model version,
confidence, tool-trace id"). Every agent module produces exactly this
shape regardless of which target DocType it's proposing a write to â€” the
gate and the BFF's Agent Action Approval DocType don't need to know
anything agent-specific.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ProposedAction(BaseModel):
    agent_type: str
    target_doctype: str
    company: str
    project: str | None
    payload: dict = Field(..., description="The draft field values, not yet applied anywhere")
    model_version: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    tool_trace_id: str
    idempotency_key: str
    requested_by_user: str
