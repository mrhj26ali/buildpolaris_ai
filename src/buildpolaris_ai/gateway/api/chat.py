"""SSE-streamed chat endpoint for the BuildPolaris copilot."""

from __future__ import annotations

import json
from typing import Any, Optional

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from buildpolaris_ai.gateway.orchestrator.schemas import ChatTurn
from buildpolaris_ai.gateway.orchestrator.turn_runner import TurnRunner
from buildpolaris_ai.platform.retrieval.connection import get_ai_db_conn

logger = structlog.get_logger()

router = APIRouter(prefix="/chat", tags=["Chat"])


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _chunk_text(text: str, chunk_size: int = 8) -> list[str]:
    """Split answer text into small streamed chunks."""
    if not text:
        return []

    words = text.split()
    chunks: list[str] = []

    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i : i + chunk_size])
        if i + chunk_size < len(words):
            chunk += " "
        chunks.append(chunk)

    return chunks


@router.post("")
async def chat(
    turn: ChatTurn,
    conn: asyncpg.Connection = Depends(get_ai_db_conn),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
):
    tenant_id = turn.tenant_id or x_tenant_id or "TENANT-ALPHA"

    async def generate():
        yield _sse_event("turn_started", {"tenant_id": tenant_id})

        try:
            runner = TurnRunner(conn=conn)
            result = await runner.run(turn, tenant_id, turn.user_context)

            if result.kind == "answer":
                for chunk in _chunk_text(result.answer or ""):
                    yield _sse_event("answer_chunk", {"chunk": chunk})

                yield _sse_event(
                    "answer_complete",
                    {
                        "answer": result.answer,
                        "citations": result.citations,
                        "citations_validated": result.citations_validated,
                        "attempts": result.attempts,
                    },
                )

            elif result.kind == "read_tool":
                yield _sse_event(
                    "read_tool_result",
                    {
                        "tool_name": result.tool_name,
                        "result": result.tool_result,
                    },
                )

            elif result.kind == "approval_required" and result.approval is not None:
                yield _sse_event(
                    "approval_required",
                    result.approval.model_dump(),
                )

            else:
                yield _sse_event(
                    "error",
                    {"error": result.error or "Unknown turn error."},
                )

        except Exception as exc:
            logger.error("Chat turn failed", error=str(exc))
            yield _sse_event("error", {"error": str(exc)})

        yield _sse_event("done", {"status": "complete"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )
