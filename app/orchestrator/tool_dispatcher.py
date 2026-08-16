"""Dispatches a navigation-intent turn to the appropriate BFF read tool
(Flowchart 4 step E: "resolve within caller's existing permitted scope").
Kept separate from turn_runner.py so the mapping from a navigation intent
to a specific MCP tool call is independently testable/reviewable.

buildpolaris_bff's MCP tool registry (ai_copilot/mcp/tool_registry.py) is
a set of project-scoped LIST/STATE tools, not a generic
find-any-record-by-name lookup -- there is no "get_record" or
"find_record" tool on the BFF side. This heuristic maps a handful of
keywords in the user's message to the closest real tool; anything that
doesn't match a specific area falls back to get_project_summary, which
is always a safe, informative default (schedule health + open-item
counts across every module, Flowcharts Â§2's dashboard-analogue view).

A more sophisticated slot-filling classifier is a natural extension
point here without touching the orchestrator or any agent.
"""
from __future__ import annotations

from app.observability.logging import get_logger
from app.orchestrator.context import TurnContext
from app.platform.bff import read_tools

logger = get_logger(__name__)

# Ordered so the first keyword match wins -- more specific terms first.
_KEYWORD_TOOL_MAP: list[tuple[tuple[str, ...], str]] = [
    (("safety", "incident", "injury"), "get_recent_safety_incidents"),
    (("punch", "punch list", "punch item"), "get_open_punch_items"),
    (("rfi", "request for information"), "get_rfi_status"),
    (("action item", "meeting"), "get_open_action_items"),
    (("evm", "earned value", "cpi", "spi"), "get_evm_summary"),
    (("budget", "cost code", "committed", "spend"), "get_budget_summary"),
    (("lookahead", "look-ahead", "look ahead", "next few weeks"), "get_lookahead"),
    (("schedule", "critical path", "task", "float", "milestone"), "get_schedule_state"),
]

_TOOL_FN = {
    "get_recent_safety_incidents": read_tools.get_recent_safety_incidents,
    "get_open_punch_items": read_tools.get_open_punch_items,
    "get_rfi_status": read_tools.get_rfi_status,
    "get_open_action_items": read_tools.get_open_action_items,
    "get_evm_summary": read_tools.get_evm_summary,
    "get_budget_summary": read_tools.get_budget_summary,
    "get_lookahead": read_tools.get_lookahead,
    "get_schedule_state": read_tools.get_schedule_state,
}


async def dispatch_navigation(context: TurnContext) -> dict:
    message = context.message.lower()
    project = context.project or ""

    if not project:
        logger.info("navigation_no_project_in_scope", trace_id=context.trace_id)
        return {"ok": False, "error": "No Project is in scope for this conversation."}

    for keywords, tool_name in _KEYWORD_TOOL_MAP:
        if any(kw in message for kw in keywords):
            fn = _TOOL_FN[tool_name]
            return await fn(context.mcp_client, project)

    return await read_tools.get_project_summary(context.mcp_client, project)
