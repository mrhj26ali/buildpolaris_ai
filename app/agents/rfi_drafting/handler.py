"""RFI Drafting Agent â€” turns a field question into a structured,
proposed RFI record (never applied directly â€” FR-8.6).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import build_proposed_action
from app.orchestrator.context import TurnContext
from app.orchestrator.contracts import AgentResult
from app.platform.model_provider.model_pin import resolve_model_version


class _DraftRFI(BaseModel):
    subject: str = Field(..., max_length=140)
    question: str
    reference_drawing_or_spec: str | None = None
    priority: str = Field(..., pattern="^(Low|Medium|High|Critical)$")
    suggested_assignee_role: str | None = None
    rationale: str


DRAFT_PROMPT = """Draft a Request for Information (RFI) from the field
description below. Be precise and unambiguous â€” an RFI response has
schedule and cost consequences, so vague questions cost the project real
time. If a drawing or spec section is mentioned or clearly implied, name
it. Set priority based on whether this blocks current field work
(Critical/High) or is informational (Low/Medium).

Field description: {message}
"""


async def run(context: TurnContext) -> AgentResult:
    prompt = DRAFT_PROMPT.format(message=context.message)
    model_version = resolve_model_version(context.company)

    draft = await context.model_provider.structured_complete(
        prompt, _DraftRFI, model_version=model_version, temperature=0.2
    )

    payload = {
        "subject": draft.subject,
        "question": draft.question,
        "reference_drawing_or_spec": draft.reference_drawing_or_spec,
        "priority": draft.priority,
        "suggested_assignee_role": draft.suggested_assignee_role,
        "project": context.project,
    }

    proposed_action = build_proposed_action(
        context, agent_type="rfi_drafting", target_doctype="RFI", payload=payload,
        model_version=model_version, confidence=0.75,
    )

    return AgentResult(proposed_action=proposed_action, rationale=draft.rationale)
