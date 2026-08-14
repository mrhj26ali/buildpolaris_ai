"""RFI drafting agent handler.

This agent proposes an RFI draft and submits it for human approval.
It never executes the write itself.
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel

from buildpolaris_ai.gateway.orchestrator.schemas import (
    AgentInvocation,
    AgentResult,
    ApprovalCard,
)
from buildpolaris_ai.platform.bff_client_factory import get_bff_client
from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.model_provider import get_model_provider
from buildpolaris_ai.platform.schemas import ActionApprovalGate

logger = structlog.get_logger()


class RFIDraft(BaseModel):
    subject: str
    description: str
    cost_impact: bool = False
    schedule_impact: bool = False


def _fallback_draft(message: str) -> tuple[RFIDraft, float]:
    subject = (message or "").strip().replace("\n", " ")[:120]
    if not subject:
        subject = "AI-drafted RFI"

    description = (
        "AI-generated RFI draft from the copilot request. "
        "Please review and confirm before submission.\n\n"
        f"Original request:\n{message.strip()}"
    )

    draft = RFIDraft(
        subject=subject,
        description=description,
        cost_impact=False,
        schedule_impact=False,
    )

    return draft, 0.55


async def handle(invocation: AgentInvocation) -> AgentResult:
    """Handle an RFI drafting request."""
    settings = get_settings()
    model_version = settings.model_provider.provider_id

    try:
        try:
            provider = get_model_provider()

            prompt = f"""
You are a construction project management assistant.

Draft an RFI based on the user's request.

Rules:
- Be concise and professional.
- Do not invent facts.
- If cost or schedule impact is not clear, set it to false.
- Return only the structured fields requested.

Request:
{invocation.message}
""".strip()

            draft = await provider.structured_generate(prompt, RFIDraft)
            confidence = 0.82

        except Exception as generation_exc:
            logger.warning(
                "RFI drafting LLM generation failed, using deterministic fallback",
                error=str(generation_exc),
            )
            draft, confidence = _fallback_draft(invocation.message)

        bff_client = get_bff_client()

        gate = ActionApprovalGate(
            ref_doctype="RFI",
            proposed_payload=draft.model_dump(),
            model_version=model_version,
            confidence_score=confidence,
            tool_trace_id=invocation.trace_id,
        )

        gate_id = await bff_client.submit_approval_gate(
            gate,
            invocation.user_context,
        )

        approval = ApprovalCard(
            gate_id=gate_id,
            agent_id=invocation.agent_id,
            ref_doctype="RFI",
            proposed_payload=draft.model_dump(),
            confidence_score=confidence,
            model_version=model_version,
            trace_id=invocation.trace_id,
            status="Pending",
        )

        return AgentResult(
            kind="approval_required",
            approval=approval,
        )

    except Exception as exc:
        logger.error("rfi_drafting agent failed", error=str(exc))
        return AgentResult(kind="error", error=str(exc))
