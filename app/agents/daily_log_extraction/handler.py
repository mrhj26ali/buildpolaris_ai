"""Daily Log Extraction Agent â€” structures a superintendent's free-text
field note into Daily Log fields. Unlike the field-capture path in
buildpolaris_pwa (which is a direct, non-AI structured form â€” FR-6.5),
this agent exists for the case where the note was captured as prose (e.g.
dictated) and needs to be structured after the fact; it still always
produces a *proposed* record, never a direct write.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import build_proposed_action
from app.orchestrator.context import TurnContext
from app.orchestrator.contracts import AgentResult
from app.platform.model_provider.model_pin import resolve_model_version


class _DailyLogExtraction(BaseModel):
    weather: str | None = None
    temperature_notes: str | None = None
    crew_count: int | None = None
    work_performed: str
    delays_or_issues: str | None = None
    safety_notes: str | None = None
    rationale: str


EXTRACTION_PROMPT = """Extract structured Daily Log fields from the field
note below. Only populate a field if the note actually states or clearly
implies it â€” leave anything unmentioned as null rather than guessing a
plausible-sounding value.

Field note: {message}
"""


async def run(context: TurnContext) -> AgentResult:
    prompt = EXTRACTION_PROMPT.format(message=context.message)
    model_version = resolve_model_version(context.company)

    extraction = await context.model_provider.structured_complete(
        prompt, _DailyLogExtraction, model_version=model_version, temperature=0.1
    )

    payload = {
        "weather": extraction.weather,
        "temperature_notes": extraction.temperature_notes,
        "crew_count": extraction.crew_count,
        "work_performed": extraction.work_performed,
        "delays_or_issues": extraction.delays_or_issues,
        "safety_notes": extraction.safety_notes,
        "project": context.project,
    }

    proposed_action = build_proposed_action(
        context, agent_type="daily_log_extraction", target_doctype="Daily Log", payload=payload,
        model_version=model_version, confidence=0.65,
    )

    return AgentResult(proposed_action=proposed_action, rationale=extraction.rationale)
