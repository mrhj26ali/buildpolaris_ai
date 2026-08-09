# src/buildpolaris_ai/platform/schemas.py
"""
Strict Pydantic schemas defining the contract between buildpolaris_bff and buildpolaris_ai.
These mirror the ERPNext/Frappe DocTypes defined in the platform spec (Section 9).
Phase 1: All mock payload shapes are derived from these models (Mock Data Fidelity Contract).
"""
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field
from uuid import uuid4


class CDCEventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class CDCEvent(BaseModel):
    """
    Payload published by buildpolaris_bff's cdc_publisher.py.
    Consumed by buildpolaris_ai's graph_sync_worker.py.
    """
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: CDCEventType
    doctype: str
    docname: str
    tenant_id: str
    project_id: str
    timestamp: datetime
    payload: dict[str, Any]


class GateStatus(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class ActionApprovalGate(BaseModel):
    """
    The payload buildpolaris_ai sends to buildpolaris_bff's agent_writes.py
    to request a guarded write action (FR-8.4, NFR-AI-6).
    """
    gate_id: Optional[str] = None
    ref_doctype: str
    ref_docname: Optional[str] = None
    initiator_type: Literal["system"] = "system"
    proposed_payload: dict[str, Any]
    status: GateStatus = GateStatus.PENDING
    model_version: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    tool_trace_id: str = Field(default_factory=lambda: str(uuid4()))


class UserContext(BaseModel):
    """
    Passed from PWA -> BFF -> AI Sidecar to enforce row-level data isolation (FR-1.5).
    The AI layer NEVER broadens this scope.
    """
    user_id: str
    tenant_id: str
    company_id: str
    assigned_project_ids: list[str]
    role: str


# ---------------------------------------------------------------------------
# Paginated Response (Phase 1 — BFF hardening)
# ---------------------------------------------------------------------------
class PaginatedResponse(BaseModel):
    """Standard paginated response envelope from the BFF."""
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    has_next: bool


# ---------------------------------------------------------------------------
# Doctype Payload Schemas — field-for-field against spec Section 9
# ---------------------------------------------------------------------------

class RFIPayload(BaseModel):
    """ERD Section 9.3 RFI"""
    rfi_id: str
    project_id: str
    raised_by: str
    assigned_to: str
    status: Literal["Draft", "Open", "Answered", "Closed"]
    cost_impact: bool
    schedule_impact: bool
    sla_due: str
    created_at: str
    subject: str
    description: str


class TaskPayload(BaseModel):
    """ERD Section 9.2 TASK"""
    task_id: str
    project_id: str
    parent_task_id: Optional[str] = None
    title: str
    start_date: str
    end_date: str
    duration: int
    total_float: float
    is_critical: bool
    status: Literal["Open", "Working", "Completed", "Cancelled"]


class DailyLogPayload(BaseModel):
    """ERD Section 9.4 DAILY_LOG"""
    log_id: str
    project_id: str
    submitted_by: str
    log_date: str
    weather: str
    labor_hours: int
    delays: str
    sync_status: str
    source: Literal["manual", "automated", "automated_confirmed"]
    capture_confidence: float = Field(ge=0.0, le=1.0)


class PunchListItemPayload(BaseModel):
    """ERD Section 9.4 PUNCH_LIST_ITEM"""
    punch_id: str
    project_id: str
    drawing_revision_id: str
    assigned_to: str
    due_date: str
    status: Literal["Open", "PendingVerification", "Closed"]
    geo_lat: float
    geo_long: float
    source: Literal["manual", "automated", "automated_confirmed"]
    capture_confidence: float = Field(ge=0.0, le=1.0)


class IncidentReportPayload(BaseModel):
    """ERD Section 9.4 INCIDENT_REPORT"""
    incident_id: str
    project_id: str
    reported_by: str
    occurred_at: str
    osha_classification: str
    description: str


class ChangeEventPayload(BaseModel):
    """ERD Section 9.6 CHANGE_EVENT"""
    event_id: str
    project_id: str
    source_doctype: Literal["RFI", "FieldIssue"]
    source_id: str
    category: Literal["scope-gap", "design-error", "field-condition", "owner-request", "other"]
    potential_cost_impact: float
    potential_schedule_impact_days: int
    status: Literal["Potential", "Validated", "Dismissed"]
    outcome_reason: str


class ContractClausePayload(BaseModel):
    """ERD Section 9.9 CONTRACT_CLAUSE"""
    clause_id: str
    source_file_id: str
    clause_type: Literal["indemnification", "liability", "termination", "other"]
    extracted_text: str
    risk_flag: Literal["None", "Low", "Medium", "High"]
    review_status: Literal["Pending", "Reviewed", "Dismissed"]
    reviewed_by: Optional[str] = None
    linked_change_event_id: Optional[str] = None


class SOVLinePayload(BaseModel):
    """ERD Section 9.6 SOV_LINE"""
    sov_line_id: str
    project_id: str
    task_id: str
    original_estimate: float
    approved_budget: float
    committed_cost: float
    revised_budget: float


class ActionApprovalGateRecord(BaseModel):
    """ERD Section 9.1 ACTION_APPROVAL_GATE — for mock seeding of gate records."""
    gate_id: str
    ref_doctype: str
    ref_docname: Optional[str] = None
    initiator_type: Literal["user", "system"]
    proposed_payload: dict[str, Any]
    status: Literal["Pending", "Approved", "Rejected"]
    approver_id: Optional[str] = None
    decided_at: Optional[str] = None
    source_version: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    trace_id: str


# ---------------------------------------------------------------------------
# Registry: doctype -> payload schema (used by seeder + contract tests)
# ---------------------------------------------------------------------------
DOCTYPE_SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "RFI": RFIPayload,
    "Task": TaskPayload,
    "DailyLog": DailyLogPayload,
    "PunchListItem": PunchListItemPayload,
    "IncidentReport": IncidentReportPayload,
    "SOVLine": SOVLinePayload,
    "ChangeEvent": ChangeEventPayload,
    "ChangeOrder": ChangeEventPayload,
    "ContractClause": ContractClausePayload,
    "ActionApprovalGate": ActionApprovalGateRecord,
}
