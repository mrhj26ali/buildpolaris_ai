"""Dispatches a navigation-intent turn to the appropriate BFF read tool
(Flowchart 4 step E: "resolve within caller's existing permitted scope").
Kept separate from turn_runner.py so the mapping from a navigation intent
to a specific MCP tool call is independently testable/reviewable.
"""
from __future__ import annotations

from app.observability.logging import get_logger
from app.orchestrator.context import TurnContext
from app.platform.bff import read_tools

logger = get_logger(__name__)


async def dispatch_navigation(context: TurnContext) -> dict:
    """v1 heuristic: if the message looks like a direct doctype+name
    reference, fetch it; otherwise treat it as a free-text find. A more
    sophisticated slot-filling classifier is a natural extension point
    here without touching the orchestrator or any agent."""
    message = context.message.strip()

    doctypes = ["RFI", "Submittal Package", "Commitment", "Task", "Daily Log", "Punch List Item"]
    for doctype in doctypes:
        if doctype.lower() in message.lower():
            return await read_tools.find_record(context.mcp_client, doctype, message)

    return await read_tools.get_project_summary(context.mcp_client, context.project or "")
