"""Strict Pydantic schemas for BFF <-> AI contract. Mirrors ERPNext DocTypes."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# =============================================================================
# CDC Events
# =============================================================================
class CDCEventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class CDCEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: CDCEventType
    doctype: str
    docname: str
    tenant_id: str
    project_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any]
    version: str = "1.0"


# =============================================================================
# Approval Gate
# =============================================================================
class GateStatus(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class ActionApprovalGate(BaseModel):
    gate_id: Optional[str] = None
    ref_doctype: str
    ref_docname: Optional[str] = None
    initiator_type: Literal["system", "user"] = "system"
    proposed_payload: dict[str, Any]
    status: GateStatus = GateStatus.PENDING
    model_version: str = "unknown"
    confidence_score: float = Field(ge=0.0, le=1.0)
    tool_trace_id: str = Field(default_factory=lambda: str(uuid4()))


# =============================================================================
# User Context
# =============================================================================
class UserContext(BaseModel):
    user_id: str
    tenant_id: str
    company_id: str
    assigned_project_ids: list[str] = Field(default_factory=list)
    role: str = "Viewer"


# =============================================================================
# Paginated Response
# =============================================================================
class PaginatedResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    has_next: bool


# =============================================================================
# RAG Response
# =============================================================================
class Citation(BaseModel):
    source_docname: str
    quoted_span: str
    relevance_score: float = 0.0


class RAGResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# =============================================================================
# Doctype Payload Schemas
# =============================================================================
class RFIPayload(BaseModel):
    rfi_id: str
    project_id: str
    raised_by: str
    assigned_to: str
    status: Literal["Draft", "Open", "Answered", "Closed"]
    cost_impact: bool = False
    schedule_impact: bool = False
    sla_due: str
    created_at: str
    subject: str
    description: str


class TaskPayload(BaseModel):
    task_id: str
    project_id: str
    parent_task_id: Optional[str] = None
    title: str
    start_date: str
    end_date: str
    duration: int
    total_float: float = 0.0
    is_critical: bool = False
    status: Literal["Open", "Working", "Completed", "Cancelled"] = "Open"
    description: str = ""


class DailyLogPayload(BaseModel):
    log_id: str
    project_id: str
    submitted_by: str
    log_date: str
    weather: str
    labor_hours: int
    delays: str = "None"
    sync_status: str = "Synced"
    source: Literal["manual", "automated", "automated_confirmed"] = "manual"
    capture_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    description: str = ""


class PunchListItemPayload(BaseModel):
    punch_id: str
    project_id: str
    drawing_revision_id: str
    assigned_to: str
    due_date: str
    status: Literal["Open", "PendingVerification", "Closed"]
    geo_lat: float = 0.0
    geo_long: float = 0.0
    source: Literal["manual", "automated", "automated_confirmed"] = "manual"
    capture_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    description: str = ""


class IncidentReportPayload(BaseModel):
    incident_id: str
    project_id: str
    reported_by: str
    occurred_at: str
    osha_classification: str
    description: str


class ChangeEventPayload(BaseModel):
    event_id: str
    project_id: str
    source_doctype: Literal["RFI", "FieldIssue", "ContractClause"]
    source_id: str
    category: Literal["scope-gap", "design-error", "field-condition", "owner-request", "other"]
    potential_cost_impact: float = 0.0
    potential_schedule_impact_days: int = 0
    status: Literal["Potential", "Validated", "Dismissed"] = "Potential"
    outcome_reason: str = ""
    description: str = ""


class ContractClausePayload(BaseModel):
    clause_id: str
    source_file_id: str
    clause_type: Literal["indemnification", "liability", "termination", "other"]
    extracted_text: str
    risk_flag: Literal["None", "Low", "Medium", "High"]
    review_status: Literal["Pending", "Reviewed", "Dismissed"] = "Pending"
    reviewed_by: Optional[str] = None
    linked_change_event_id: Optional[str] = None
    description: str = ""


class SOVLinePayload(BaseModel):
    sov_line_id: str
    project_id: str
    task_id: str
    original_estimate: float
    approved_budget: float
    committed_cost: float = 0.0
    revised_budget: float = 0.0
    description: str = ""


class ActionApprovalGateRecord(BaseModel):
    gate_id: str
    ref_doctype: str
    ref_docname: Optional[str] = None
    initiator_type: Literal["user", "system"]
    proposed_payload: dict[str, Any]
    status: Literal["Pending", "Approved", "Rejected"]
    approver_id: Optional[str] = None
    decided_at: Optional[str] = None
    source_version: str = "v1.0"
    confidence_score: float = Field(ge=0.0, le=1.0)
    trace_id: str
    description: str = ""


# =============================================================================
# Registry
# =============================================================================
DOCTYPE_SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "RFI": RFIPayload,
    "Task": TaskPayload,
    "DailyLog": DailyLogPayload,
    "PunchListItem": PunchListItemPayload,
    "IncidentReport": IncidentReportPayload,
    "SOVLine": SOVLinePayload,
    "ChangeEvent": ChangeEventPayload,
    "ContractClause": ContractClausePayload,
    "ActionApprovalGate": ActionApprovalGateRecord,
}
