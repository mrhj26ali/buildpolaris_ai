"""BFFMCPClient â€” Streamable HTTP MCP client calling buildpolaris_bff's
MCP server (ARCH Â§4.2 Direction 2: "AI is a client calling BFF's MCP
server", read-only tools only in v1). This wraps the `mcp` SDK's
streamable-http client transport so orchestrator/tool_dispatcher.py never
has to know MCP protocol details â€” it just calls `list_tools()` /
`call_tool()`.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from app.config import get_settings
from app.gateway.auth.scope_assertion import ScopeAssertion
from app.gateway.auth.on_behalf_of import build_on_behalf_of_headers
from app.observability.logging import get_logger

logger = get_logger(__name__)


class BFFMCPClient:
    """One instance per copilot turn â€” carries the Scope Assertion for
    that turn so every tool call it makes is on-behalf-of the same asserted
    user (never re-minted, never escalated)."""

    def __init__(self, assertion: ScopeAssertion, raw_assertion_token: str) -> None:
        self._settings = get_settings().bff
        self._headers = build_on_behalf_of_headers(
            assertion, self._settings.service_key.get_secret_value(), raw_assertion_token
        )

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[Any]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(
            self._settings.mcp_url, headers=self._headers,
        ) as (read_stream, write_stream, _get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def list_tools(self) -> list[dict]:
        async with self._session() as session:
            result = await session.list_tools()
            return [{"name": t.name, "description": t.description} for t in result.tools]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        async with self._session() as session:
            result = await session.call_tool(name, arguments)
            if result.isError:
                logger.warning("mcp_tool_call_error", tool=name, arguments=arguments)
            # MCP tool results are a list of content blocks; read-only
            # tools here always return exactly one text/JSON block.
            for block in result.content:
                if hasattr(block, "text"):
                    import json

                    try:
                        return json.loads(block.text)
                    except (json.JSONDecodeError, TypeError):
                        return {"text": block.text}
            return {}
