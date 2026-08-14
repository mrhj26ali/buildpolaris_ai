"""Contract clause extraction agent (FR-8.8, UC-8.7)."""
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


class ExtractedClause(BaseModel):
    clause_type: str = Field(description="Type: indemnification, liability, termination, other")
    extracted_text: str = Field(description="The extracted clause text")
    risk_flag: str = Field(description="Risk level: None, Low, Medium, High")
    risk_reason: str = Field(description="Brief reason for the risk flag")


class ContractAnalysis(BaseModel):
    clauses: list[ExtractedClause] = Field(default_factory=list)
    overall_risk_summary: str = Field(default="")


async def handle(invocation: AgentInvocation) -> AgentResult:
    """Scan contract text and extract classified clauses."""
    settings = get_settings()
    model_version = settings.model_provider.primary_provider

    try:
        provider = get_model_provider()
        prompt = f"""You are a construction contract legal analyst.
Analyze the following contract text and extract key clauses.
Classify each as: indemnification, liability, termination, or other.
Assign a risk flag: None, Low, Medium, High.

Contract Text:
{invocation.message[:3000]}

Extract all significant clauses with their risk assessment."""

        analysis = await provider.structured_generate(prompt, ContractAnalysis)
        confidence = 0.80

    except Exception as e:
        logger.error("Contract clause extraction failed", error=str(e))
        return AgentResult(kind="error", error=f"Extraction failed: {str(e)}")

    # Submit for human review (FR-8.8: never writes directly to budget/schedule)
    bff_client = get_bff_client()
    gate = ActionApprovalGate(
        ref_doctype="ContractClause",
        proposed_payload={"clauses": [c.model_dump() for c in analysis.clauses], "summary": analysis.overall_risk_summary},
        model_version=model_version,
        confidence_score=confidence,
        tool_trace_id=invocation.trace_id,
    )
    gate_id = await bff_client.submit_approval_gate(gate, invocation.user_context)

    approval = ApprovalCard(
        gate_id=gate_id,
        agent_id=invocation.agent_id,
        ref_doctype="ContractClause",
        proposed_payload={"clauses": [c.model_dump() for c in analysis.clauses]},
        confidence_score=confidence,
        model_version=model_version,
        trace_id=invocation.trace_id,
        status="Pending",
    )

    return AgentResult(kind="approval_required", approval=approval)
