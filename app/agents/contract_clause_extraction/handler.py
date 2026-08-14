"""Contract Clause Extraction Agent â€” pulls key commercial terms out of
an already-ingested Commitment contract's indexed chunks. Explicitly out
of scope (per REQ v2.1's non-goals): this agent never writes to Budget or
Schedule directly, even though payment terms and liquidated-damages
clauses are financially significant â€” it only proposes Commitment field
updates, same as every other agent here (FR-8.6).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import build_proposed_action
from app.orchestrator.context import TurnContext
from app.orchestrator.contracts import AgentResult
from app.platform.model_provider.model_pin import resolve_model_version


class _ContractTerms(BaseModel):
    payment_terms: str | None = None
    retention_percent: float | None = None
    liquidated_damages_per_day: str | None = None
    notice_period_days: int | None = None
    key_clauses_cited: list[str] = Field(default_factory=list)
    rationale: str


EXTRACTION_PROMPT = """Extract key commercial terms from the contract
context below. Every value you populate must be traceable to a specific
clause in the context â€” list the clause references in
key_clauses_cited. Leave a field null if the contract text provided
doesn't clearly state it; do not infer from general construction-industry
convention.

Contract context:
{context}

Extraction focus (from the user's request): {message}
"""


async def run(context: TurnContext) -> AgentResult:
    from app.dependencies import get_rag_service

    rag_service = get_rag_service()
    grounding = await rag_service.answer(
        f"payment terms, retention, liquidated damages, notice periods relevant to: {context.message}",
        context.company, context.project,
    )

    prompt = EXTRACTION_PROMPT.format(context=grounding.text, message=context.message)
    model_version = resolve_model_version(context.company)

    terms = await context.model_provider.structured_complete(
        prompt, _ContractTerms, model_version=model_version, temperature=0.1
    )

    payload = {
        "payment_terms": terms.payment_terms,
        "retention_percent": terms.retention_percent,
        "liquidated_damages_per_day": terms.liquidated_damages_per_day,
        "notice_period_days": terms.notice_period_days,
        "key_clauses_cited": terms.key_clauses_cited,
        "project": context.project,
    }

    proposed_action = build_proposed_action(
        context, agent_type="contract_clause_extraction", target_doctype="Commitment",
        payload=payload, model_version=model_version, confidence=0.7,
    )

    return AgentResult(proposed_action=proposed_action, rationale=terms.rationale)
