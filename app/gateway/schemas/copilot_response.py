"""Non-streaming shape of a copilot turn's result â€” also what each SSE
'done' event carries (ARCH Â§4.5, sse_events.py streams the incremental
version of this).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """FR-8.3 / NFR-UX.4 â€” every cited claim must show a real,
    human-meaningful reference, never a hidden one."""

    source_doctype: str
    source_name: str
    span_type: str
    span_start: int
    span_end: int
    quoted_span: str


class PendingApprovalCard(BaseModel):
    """Rendered instead of an applied change â€” FR-8.6."""

    approval_id: str | None = None  # set once BFF has persisted the row
    agent_type: str
    target_doctype: str
    proposed_payload: dict
    model_version: str
    confidence: float
    tool_trace_id: str


class CopilotResponse(BaseModel):
    kind: Literal["navigation", "grounded_answer", "tool_result", "pending_approval", "refusal"]
    text: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    pending_approval: PendingApprovalCard | None = None
    ai_generated: bool = True  # FR-8.9 â€” persistent, unambiguous disclosure
    model_version: str
    trace_id: str
