"""BFFMCPClient -- client for buildpolaris_bff's MCP tool surface
(ARCH v2.1 Direction 2: "AI is a client calling BFF's MCP server",
read-only tools only in v1).

IMPORTANT: buildpolaris_bff/ai_copilot/mcp/mcp_server.py deliberately
does NOT implement the real MCP Streamable-HTTP transport/handshake --
its own module docstring explains why: "a separate ASGI Streamable-HTTP
process [would be] unwarranted complexity for a single internal consumer
that already speaks plain HTTP+JSON." It exposes exactly two plain
@frappe.whitelist() JSON endpoints:

    buildpolaris_bff.ai_copilot.mcp.mcp_server.list_tools
    buildpolaris_bff.ai_copilot.mcp.mcp_server.call_tool

A previous version of this file used the `mcp` Python SDK's
streamablehttp_client, which performs a real MCP session
initialize/handshake -- that can never succeed against a Frappe
whitelisted method, since Frappe doesn't implement that protocol. This
version speaks BFF's actual (simpler) contract directly.

Authorization is two-layered, matching BFF's own module docstring:
  1. Transport identity: `Authorization: token key:secret` for the
     low-privilege 'BuildPolaris AI Service' account (BFFClient).
  2. Actual authorization: the Scope Assertion's asserted user's own
     Role/Project permissions, sent as an explicit `scope_assertion`
     body field and re-verified by BFF on every call.
"""
from __future__ import annotations

from app.gateway.auth.scope_assertion import ScopeAssertion
from app.observability.logging import get_logger
from app.platform.bff.bff_client import BFFClient, BFFCallError

logger = get_logger(__name__)


class BFFMCPClient:
    """One instance per copilot turn -- carries the Scope Assertion for
    that turn so every tool call it makes is on-behalf-of the same
    asserted user (never re-minted, never escalated)."""

    def __init__(self, assertion: ScopeAssertion, raw_assertion_token: str) -> None:
        self._assertion = assertion
        self._raw_assertion_token = raw_assertion_token
        self._client = BFFClient()

    async def list_tools(self) -> list[dict]:
        settings = self._client.settings
        result = await self._client.post(settings.list_tools_path, json={})
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict) -> dict:
        settings = self._client.settings
        payload = {
            "tool_name": name,
            "arguments": arguments,
            "scope_assertion": self._raw_assertion_token,
            "trace_id": None,
        }
        try:
            result = await self._client.post(settings.call_tool_path, json=payload)
        except BFFCallError:
            logger.warning("mcp_tool_call_transport_error", tool=name)
            return {"ok": False, "error": "buildpolaris_bff unreachable"}

        # mcp_server.call_tool()'s own return shape is {"ok": bool, "result"|"error": ...}
        # and passes through BFFClient._unwrap() as the whitelisted method's
        # "data" (there is no ai_copilot.api-style success() envelope on
        # this specific endpoint -- it returns its dict directly).
        if not isinstance(result, dict) or "ok" not in result:
            # Still went through envelope unwrapping fine, just be defensive.
            return {"ok": True, "result": result}
        if not result.get("ok"):
            logger.warning("mcp_tool_call_error", tool=name, error=result.get("error"))
        return result
