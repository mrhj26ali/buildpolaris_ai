"""POST /copilot/message â€” the one conversational copilot surface
(ARCH Flowchart 4). Streams via SSE (ARCH Â§4.5) so the PWA/BFF proxy
never buffers a full response before the user sees anything.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Request
from sse_starlette.sse import EventSourceResponse

from app.gateway.auth.scope_assertion import ScopeAssertion, verify_scope_assertion
from app.gateway.auth.service_credential import verify_service_credential
from app.gateway.schemas.copilot_request import CopilotMessageRequest
from app.gateway.schemas.copilot_response import Citation, CopilotResponse, PendingApprovalCard
from app.observability.logging import get_logger
from app.observability.tracing import get_trace_id
from app.orchestrator.agent_registry import AgentRegistry, get_agent_registry
from app.orchestrator.context import TurnContext
from app.orchestrator.turn_runner import TurnResult
from app.platform.bff.mcp_client import BFFMCPClient
from app.platform.model_provider.factory import get_model_provider

logger = get_logger(__name__)

router = APIRouter(
    prefix="/copilot", tags=["copilot"], dependencies=[Depends(verify_service_credential)]
)


def _turn_result_to_response(result: TurnResult, trace_id: str) -> CopilotResponse:
    if result.kind == "navigation":
        return CopilotResponse(
            kind="navigation", text=json.dumps(result.navigation_result),
            model_version="n/a", trace_id=trace_id,
        )
    if result.kind in ("grounded_answer", "refusal") and result.rag_answer is not None:
        return CopilotResponse(
            kind=result.kind, text=result.rag_answer.text,
            citations=[
                Citation(
                    source_doctype=c.source_doctype, source_name=c.source_name,
                    span_type=c.span_type, span_start=c.span_start, span_end=c.span_end,
                    quoted_span=c.quoted_span,
                )
                for c in result.rag_answer.citations
            ],
            model_version=result.model_version, trace_id=trace_id,
        )
    if result.kind == "pending_approval":
        return CopilotResponse(
            kind="pending_approval", text=result.text,
            pending_approval=PendingApprovalCard(
                approval_id=result.approval_ref, agent_type=result.agent_type or "",
                target_doctype="", proposed_payload=result.proposed_payload or {},
                model_version=result.model_version, confidence=0.0,
                tool_trace_id=result.approval_ref or "",
            ),
            model_version=result.model_version, trace_id=trace_id,
        )
    return CopilotResponse(kind="refusal", text="Unable to process this request.",
                            model_version="n/a", trace_id=trace_id)


@router.post("/message")
async def post_message(
    body: CopilotMessageRequest,
    request: Request,
    x_scope_assertion: str = Header(...),
    assertion: ScopeAssertion = Depends(verify_scope_assertion),
    registry: AgentRegistry = Depends(get_agent_registry),
):
    """Streams disclosure -> tokens/citations -> done, per ARCH Â§4.5.
    Non-streaming callers can simply read the final 'done' event's payload
    (it carries the same shape as CopilotResponse).
    """
    trace_id = get_trace_id()

    async def event_generator():
        yield {"event": "disclosure", "data": json.dumps({"ai_generated": True})}

        try:
            provider = get_model_provider()
            mcp_client = BFFMCPClient(assertion, x_scope_assertion)

            context = TurnContext(
                thread_id=body.thread_id, message=body.message,
                history=[h.model_dump() for h in body.history],
                assertion=assertion, raw_assertion_token=x_scope_assertion,
                trace_id=trace_id, model_provider=provider, mcp_client=mcp_client,
            )

            from app.platform.citations.citation_validator import CitationValidator
            from app.platform.graph_store.age_adapter import AgeGraphAdapter
            from app.platform.rag.embedder import Embedder
            from app.platform.rag.rag_service import RagService
            from app.platform.rag.retriever import Retriever
            from app.platform.vector_store.pgvector_adapter import PgVectorAdapter
            from app.db.postgres import get_pool

            async with get_pool().acquire() as conn:
                vector_store = PgVectorAdapter(conn)
                graph_store = AgeGraphAdapter(conn)
                retriever = Retriever(vector_store, graph_store, Embedder(provider))
                rag_service = RagService(
                    vector_store, graph_store, provider, retriever, CitationValidator()
                )

                from app.orchestrator.turn_runner import TurnRunner

                runner = TurnRunner(registry, rag_service)
                result = await runner.run_turn(context)

            response = _turn_result_to_response(result, trace_id)

            if response.text:
                # Token-level streaming of a fully-generated answer still
                # gives the "reads as alive, not hung" UX Â§4.5 asks for,
                # without needing the model provider's own token stream
                # wired through every provider adapter in v1.
                for chunk in _chunk_text(response.text):
                    yield {"event": "token", "data": json.dumps({"text": chunk})}

            for citation in response.citations:
                yield {
                    "event": "citation",
                    "data": json.dumps(citation.model_dump()),
                }

            yield {
                "event": "done",
                "data": response.model_dump_json(),
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("copilot_turn_failed", trace_id=trace_id)
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(event_generator())


def _chunk_text(text: str, size: int = 24):
    for i in range(0, len(text), size):
        yield text[i : i + size]
