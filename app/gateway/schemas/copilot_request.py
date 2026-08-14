"""POST /copilot/message request body (UC-8.1 step 2)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CopilotMessageRequest(BaseModel):
    thread_id: str = Field(..., description="Copilot Thread name (BFF-owned DocType)")
    message: str = Field(..., min_length=1, max_length=8000)
    history: list["CopilotHistoryTurn"] = Field(default_factory=list)


class CopilotHistoryTurn(BaseModel):
    role: str  # 'user' | 'assistant'
    content: str


CopilotMessageRequest.model_rebuild()
