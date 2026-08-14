"""v1 Copilot endpoints: chat + agent invocation."""
from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from buildpolaris_ai.gateway.middleware.tenant_auth import get_user_context
from buildpolaris_ai.gateway.orchestrator.schemas import ChatTurn, AgentInvocation
from buildpolaris_ai.gateway.orchestrator.turn_runner import TurnRunner
from buildpolaris_ai.platform.retrieval.connection import get_ai_db_conn
from buildpolaris_ai.platform.schemas import UserContext

logger = structlog.get_logger()
router = APIRouter(prefix="/copilot", tags=["v1 Copilot"])


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/message")
async def copilot_message(
    turn: ChatTurn,
    user_ctx: UserContext = Depends(get_user_context),
    conn=Depends(get_ai_db_conn),
):
    """UC-8.1/8.2: Grounded Q&A with citations."""
    turn.tenant_id = user_ctx.tenant_id
    turn.user_context = user_ctx

    async def generate():
        yield _sse_event("turn_started", {"tenant_id": user_ctx.tenant_id})
        try:
            runner = TurnRunner(conn=conn)
            result = await runner.run(turn, user_ctx.tenant_id, user_ctx)

            if result.kind == "answer":
                yield _sse_event("answer_complete", {
                    "answer": result.answer,
                    "citations": result.citations,
                    "citations_validated": result.citations_validated,
                    "attempts": result.attempts,
                })
            elif result.kind == "approval_required" and result.approval:
                yield _sse_event("approval_required", result.approval.model_dump())
            elif result.kind == "read_tool":
                yield _sse_event("read_tool_result", {
                    "tool_name": result.tool_name,
                    "result": result.tool_result,
                })
            else:
                yield _sse_event("error", {"error": result.error or "Unknown error"})
        except Exception as exc:
            logger.error("Copilot message failed", error=str(exc))
            yield _sse_event("error", {"error": str(exc)})
        yield _sse_event("done", {"status": "complete"})

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/agent")
async def copilot_agent(
    invocation: AgentInvocation,
    user_ctx: UserContext = Depends(get_user_context),
    conn=Depends(get_ai_db_conn),
):
    """UC-8.4: Invoke a specific agent."""
    invocation.tenant_id = user_ctx.tenant_id
    invocation.user_context = user_ctx

    turn = ChatTurn(
        message=invocation.message,
        route="agent",
        agent_id=invocation.agent_id,
        tenant_id=user_ctx.tenant_id,
        user_context=user_ctx,
    )
    runner = TurnRunner(conn=conn)
    result = await runner.run(turn, user_ctx.tenant_id, user_ctx)
    return result.model_dump()
