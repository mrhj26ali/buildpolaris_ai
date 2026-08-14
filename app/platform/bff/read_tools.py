"""Read-only tool catalog this sidecar knows how to call on BFF's MCP
server (UC-8.2 â€” navigation intent resolves within the caller's existing
permitted scope). Kept as named, typed wrapper functions rather than
leaving orchestrator/tool_dispatcher.py to build raw tool-call dicts
inline, so adding/removing a read tool is a one-place change.

The actual permission enforcement happens BFF-side (has_permission against
the on-behalf-of user, per the forwarded Scope Assertion) â€” this module
only shapes the call, it grants nothing.
"""
from __future__ import annotations

from app.platform.bff.mcp_client import BFFMCPClient


async def find_record(client: BFFMCPClient, doctype: str, query: str) -> dict:
    """Navigation intent â€” 'find the RFI about the elevator shaft'."""
    return await client.call_tool("find_record", {"doctype": doctype, "query": query})


async def get_record(client: BFFMCPClient, doctype: str, name: str) -> dict:
    return await client.call_tool("get_record", {"doctype": doctype, "name": name})


async def list_open_items(client: BFFMCPClient, doctype: str, project: str | None) -> dict:
    """'What RFIs are still open on this project' â€” a bounded list query,
    not free-text search."""
    return await client.call_tool("list_open_items", {"doctype": doctype, "project": project})


async def get_project_summary(client: BFFMCPClient, project: str) -> dict:
    return await client.call_tool("get_project_summary", {"project": project})
