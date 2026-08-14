"""Orchestrator schemas for chat turns, agent invocations, and results."""

from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from buildpolaris_ai.platform.schemas import UserContext


class ChatTurn(BaseModel):
    """Incoming chat turn from the PWA or another client."""

    message: str
    route: Optional[Literal["auto", "rag", "read_tool", "agent"]] = "auto"
    tool: Optional[str] = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    agent_id: Optional[str] = None
    tenant_id: Optional[str] = None
    user_context: Optional[UserContext] = None


class AgentInvocation(BaseModel):
    """The normalized invocation payload passed to an agent handler."""

    agent_id: str
    message: str
    tenant_id: str
    user_context: UserContext
    args: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = Field(default_factory=lambda: str(uuid4()))


class ApprovalCard(BaseModel):
    """The pending-approval card emitted when an agent proposes a write."""

    gate_id: str
    agent_id: str
    ref_doctype: str
    proposed_payload: dict[str, Any]
    confidence_score: float
    model_version: str
    trace_id: str
    status: Literal["Pending", "Approved", "Rejected"] = "Pending"


class AgentResult(BaseModel):
    """Uniform result shape returned by the turn runner and agents."""

    kind: Literal["answer", "read_tool", "approval_required", "error"]
    answer: Optional[str] = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    citations_validated: Optional[bool] = None
    attempts: Optional[int] = None
    tool_name: Optional[str] = None
    tool_result: Optional[Any] = None
    approval: Optional[ApprovalCard] = None
    error: Optional[str] = None
