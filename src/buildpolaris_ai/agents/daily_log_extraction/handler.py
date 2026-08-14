"""Daily Log field extraction agent (FR-8.7, UC-8.6)."""
from __future__ import annotations

from pydantic import BaseModel, Field

import structlog

from buildpolaris_ai.gateway.orchestrator.schemas import (
    AgentInvocation, AgentResult, ApprovalCard,
)
from buildpolaris_ai.platform.bff_client_factory import get_bff_client
from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.model_provider import get_model_provider
from buildpolaris_ai.platform.schemas import ActionApprovalGate

logger = structlog.get_logger()


class ExtractedDailyLog(BaseModel):
    weather: str = Field(description="Weather conditions observed")
    labor_hours: int = Field(description="Total labor hours worked")
    workforce_count: int = Field(description="Number of workers on site")
    work_performed: str = Field(description="Summary of work performed")
    delays: str = Field(default="None", description="Any delays encountered")
    equipment_used: str = Field(default="", description="Equipment used")
    safety_notes: str = Field(default="", description="Safety observations")


async def handle(invocation: AgentInvocation) -> AgentResult:
    """Extract structured Daily Log fields from text/speech transcript."""
    settings = get_settings()
    model_version = settings.model_provider.primary_provider

    try:
        provider = get_model_provider()
        prompt = f"""You are a construction field data extraction specialist.
Extract structured Daily Log fields from the following field report text.
Be precise. If a field cannot be determined, use reasonable defaults.

Field Report:
{invocation.message}

Extract: weather, labor_hours, workforce_count, work_performed, delays, equipment_used, safety_notes."""

        extracted = await provider.structured_generate(prompt, ExtractedDailyLog)
        confidence = 0.85

    except Exception as e:
        logger.warning("Daily log extraction LLM failed, using fallback", error=str(e))
        # Deterministic fallback
        extracted = ExtractedDailyLog(
            weather="Unknown",
            labor_hours=8,
            workforce_count=1,
            work_performed=invocation.message[:200],
            delays="None",
        )
        confidence = 0.5

    # Submit for approval (FR-8.6: writes require human approval)
    bff_client = get_bff_client()
    gate = ActionApprovalGate(
        ref_doctype="DailyLog",
        proposed_payload=extracted.model_dump(),
        model_version=model_version,
        confidence_score=confidence,
        tool_trace_id=invocation.trace_id,
    )
    gate_id = await bff_client.submit_approval_gate(gate, invocation.user_context)

    approval = ApprovalCard(
        gate_id=gate_id,
        agent_id=invocation.agent_id,
        ref_doctype="DailyLog",
        proposed_payload=extracted.model_dump(),
        confidence_score=confidence,
        model_version=model_version,
        trace_id=invocation.trace_id,
        status="Pending",
    )

    return AgentResult(kind="approval_required", approval=approval)
