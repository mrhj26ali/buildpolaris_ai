"""Intent classification â€” Flowchart 4 step C ("buildpolaris_ai classifies
intent") + step D's three-way branch: navigation, grounded factual
question, or proposed action.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from app.observability.logging import get_logger
from app.orchestrator.agent_registry import AgentRegistry
from app.platform.model_provider.adapter import ModelProviderAdapter

logger = get_logger(__name__)


class IntentType(str, Enum):
    NAVIGATION = "navigation"
    GROUNDED_QUESTION = "grounded_question"
    PROPOSED_ACTION = "proposed_action"


class _IntentClassification(BaseModel):
    intent_type: IntentType
    agent_type: str | None = None  # populated only when intent_type == proposed_action


CLASSIFY_PROMPT = """Classify the user's request into exactly one category:

- "navigation": they want to find or open something that already exists
  (a record, screen, or link) â€” e.g. "show me RFI-042", "find the punch
  list for Building B".
- "grounded_question": they're asking a factual question that should be
  answered from indexed project documents, with citations â€” e.g. "what
  does the contract say about liquidated damages".
- "proposed_action": they want something drafted or created that would
  become a new or modified record â€” e.g. "draft an RFI about the beam
  clash", "review this submittal against the spec".

If proposed_action, also identify which of these agent types best fits:
{agent_types}

User message: {message}
"""


async def classify_intent(
    message: str, provider: ModelProviderAdapter, registry: AgentRegistry
) -> tuple[IntentType, str | None]:
    manifests = registry.all_manifests()
    agent_type_list = "\n".join(f"- {m.agent_type}: {m.description}" for m in manifests)

    prompt = CLASSIFY_PROMPT.format(agent_types=agent_type_list, message=message)
    try:
        result = await provider.structured_complete(prompt, _IntentClassification, temperature=0.0)
        return result.intent_type, result.agent_type
    except Exception as exc:  # noqa: BLE001
        logger.warning("intent_classification_failed_falling_back", error=str(exc))
        matched = registry.match_intent(message)
        if matched:
            return IntentType.PROPOSED_ACTION, matched
        return IntentType.GROUNDED_QUESTION, None
