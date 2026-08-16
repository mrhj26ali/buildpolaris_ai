"""Read-only tool catalog this sidecar knows how to call on BFF's MCP
surface (UC-8.2 -- navigation intent / grounded questions resolve within
the caller's existing permitted scope).

Named, typed wrapper functions over BFFMCPClient.call_tool(), one per
entry in buildpolaris_bff/ai_copilot/mcp/tool_registry.py's TOOLS dict --
that registry is the source of truth for tool NAMES; a tool added there
without a matching wrapper here is still callable via call_tool()
directly, it just won't have a typed helper.

The actual permission enforcement happens BFF-side (has_permission
against the on-behalf-of user, per the forwarded Scope Assertion) --
this module only shapes the call, it grants nothing.
"""
from __future__ import annotations

from app.platform.bff.mcp_client import BFFMCPClient


async def get_schedule_state(client: BFFMCPClient, project: str) -> dict:
    """A Project's Tasks with CPM outputs (critical path, float, dates)."""
    return await client.call_tool("get_schedule_state", {"project": project})


async def get_lookahead(client: BFFMCPClient, project: str, weeks: int | None = None,
                         as_of_date: str | None = None) -> dict:
    """N-week look-ahead schedule for a Project."""
    args: dict = {"project": project}
    if weeks is not None:
        args["weeks"] = weeks
    if as_of_date is not None:
        args["as_of_date"] = as_of_date
    return await client.call_tool("get_lookahead", args)


async def get_budget_summary(client: BFFMCPClient, project: str) -> dict:
    """Budget vs. committed vs. actual per Cost Code on a Project."""
    return await client.call_tool("get_budget_summary", {"project": project})


async def get_evm_summary(client: BFFMCPClient, project: str, as_of_date: str | None = None) -> dict:
    """Earned Value Management snapshot (CPI/SPI) for a Project."""
    args: dict = {"project": project}
    if as_of_date is not None:
        args["as_of_date"] = as_of_date
    return await client.call_tool("get_evm_summary", args)


async def get_rfi_status(client: BFFMCPClient, project: str) -> dict:
    """A Project's RFIs with status, assignee, due date."""
    return await client.call_tool("get_rfi_status", {"project": project})


async def get_open_action_items(client: BFFMCPClient, project: str) -> dict:
    """A Project's open meeting Action Items."""
    return await client.call_tool("get_open_action_items", {"project": project})


async def get_open_punch_items(client: BFFMCPClient, project: str) -> dict:
    """A Project's open Punch List items."""
    return await client.call_tool("get_open_punch_items", {"project": project})


async def get_recent_safety_incidents(client: BFFMCPClient, project: str) -> dict:
    """A Project's Safety Incidents (metadata only)."""
    return await client.call_tool("get_recent_safety_incidents", {"project": project})


async def get_project_summary(client: BFFMCPClient, project: str) -> dict:
    """Cross-module dashboard summary for a Project (added alongside the
    buildpolaris_bff Project module -- see tool_registry.py)."""
    return await client.call_tool("get_project_summary", {"project": project})
