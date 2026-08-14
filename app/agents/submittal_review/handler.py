"""Submittal Review Agent â€” compares a submittal's content against
already-indexed spec chunks (via RagService's retrieval, not a fresh
upload) and proposes a review outcome. Grounded in retrieved citations so
the proposed comments always trace back to a real spec passage.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import build_proposed_action
from app.orchestrator.context import TurnContext
from app.orchestrator.contracts import AgentResult
from app.platform.model_provider.model_pin import resolve_model_version


class _SubmittalReview(BaseModel):
    review_status: str = Field(..., pattern="^(Approved|Approved as Noted|Revise and Resubmit|Rejected)$")
    comments: str
    cited_spec_sections: list[str] = Field(default_factory=list)
    rationale: str


REVIEW_PROMPT = """Review the submittal described below against the spec
passages provided as context. Propose one of the four standard review
outcomes (Approved / Approved as Noted / Revise and Resubmit / Rejected).
Every comment you make must be traceable to a specific spec passage in
the context â€” never invent a requirement that isn't in the retrieved
spec text.

Spec context:
{context}

Submittal description: {message}
"""


async def run(context: TurnContext) -> AgentResult:
    # Grounding retrieval â€” reuse the same vector search the RAG path
    # uses, scoped to this project's indexed spec documents, rather than
    # re-implementing retrieval inside the agent.
    from app.dependencies import get_rag_service

    rag_service = get_rag_service()
    grounding = await rag_service.answer(
        f"spec requirements relevant to: {context.message}", context.company, context.project
    )

    prompt = REVIEW_PROMPT.format(context=grounding.text, message=context.message)
    model_version = resolve_model_version(context.company)

    review = await context.model_provider.structured_complete(
        prompt, _SubmittalReview, model_version=model_version, temperature=0.15
    )

    payload = {
        "review_status": review.review_status,
        "comments": review.comments,
        "cited_spec_sections": review.cited_spec_sections,
        "project": context.project,
    }

    proposed_action = build_proposed_action(
        context, agent_type="submittal_review", target_doctype="Submittal Item", payload=payload,
        model_version=model_version, confidence=0.7,
    )

    return AgentResult(proposed_action=proposed_action, rationale=review.rationale)
