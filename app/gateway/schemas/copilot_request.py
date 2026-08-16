"""POST /copilot/message request body (UC-8.1 step 2).

Field names match what buildpolaris_bff's copilot_gateway_service.py
actually sends: `text` (not `message`) and an optional `thread_id` (a
brand-new thread has none yet -- BFF creates the Copilot Thread record
itself and doesn't have a name to send until after that insert, so this
must accept null on the first turn of a conversation).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CopilotHistoryTurn(BaseModel):
    role: str  # 'user' | 'assistant'
    content: str


class CopilotMessageRequest(BaseModel):
    thread_id: str | None = Field(default=None, description="Copilot Thread name (BFF-owned DocType), null on the first turn")
    text: str = Field(..., min_length=1, max_length=8000)
    history: list[CopilotHistoryTurn] = Field(default_factory=list)
    project: str | None = None
