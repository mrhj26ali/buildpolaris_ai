"""TurnRunner â€” executes one copilot turn end-to-end (ARCH Flowchart 4,
the whole diagram). This is the orchestrator's top-level entrypoint;
gateway/routers/copilot_message.py calls exactly this and streams its
result.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.observability.logging import get_logger
from app.observability.metrics import AGENT_RUNS_TOTAL, COPILOT_REQUESTS_TOTAL, counters
from app.orchestrator.agent_registry import AgentRegistry
from app.orchestrator.context import TurnContext
from app.orchestrator.intent_classifier import IntentType, classify_intent
from app.orchestrator.tool_dispatcher import dispatch_navigation
from app.platform.governance.action_approval_gate import ActionApprovalGateClient
from app.platform.rag.rag_service import RagAnswer, RagService

logger = get_logger(__name__)


@dataclass(slots=True)
class TurnResult:
    kind: str  # 'navigation' | 'grounded_answer' | 'pending_approval' | 'refusal'
    text: str | None = None
    rag_answer: RagAnswer | None = None
    navigation_result: dict | None = None
    approval_ref: str | None = None
    agent_type: str | None = None
    proposed_payload: dict | None = None
    model_version: str = ""


class TurnRunner:
    def __init__(self, registry: AgentRegistry, rag_service: RagService) -> None:
        self._registry = registry
        self._rag_service = rag_service

    async def run_turn(self, context: TurnContext) -> TurnResult:
        counters.increment(COPILOT_REQUESTS_TOTAL)

        intent_type, agent_type = await classify_intent(
            context.message, context.model_provider, self._registry
        )
        logger.info(
            "turn_intent_classified", intent_type=intent_type.value, agent_type=agent_type,
            trace_id=context.trace_id,
        )

        if intent_type == IntentType.NAVIGATION:
            result = await dispatch_navigation(context)
            return TurnResult(kind="navigation", navigation_result=result)

        if intent_type == IntentType.GROUNDED_QUESTION:
            answer = await self._rag_service.answer(context.message, context.company, context.project)
            kind = "refusal" if answer.refused else "grounded_answer"
            return TurnResult(kind=kind, rag_answer=answer, model_version=answer.model_version)

        # proposed_action
        if agent_type is None:
            logger.warning("proposed_action_with_no_agent_type_falling_back_to_rag")
            answer = await self._rag_service.answer(context.message, context.company, context.project)
            return TurnResult(
                kind="refusal" if answer.refused else "grounded_answer",
                rag_answer=answer, model_version=answer.model_version,
            )

        module = self._registry.get_module(agent_type)
        counters.increment(AGENT_RUNS_TOTAL)
        agent_result = await module.run(context)

        gate = ActionApprovalGateClient(context.raw_assertion_token)
        approval_ref = await gate.propose(agent_result.proposed_action)

        return TurnResult(
            kind="pending_approval",
            text=agent_result.rationale,
            approval_ref=approval_ref,
            agent_type=agent_type,
            proposed_payload=agent_result.proposed_action.payload,
            model_version=agent_result.proposed_action.model_version,
        )
