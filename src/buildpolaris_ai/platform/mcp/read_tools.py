"""Read-only MCP tool surface.

This module is the MCP transport wrapper.
The actual tool implementations live in read_tools_impl.py so the orchestrator
and unit tests do not depend on FastMCP being importable.

Read-only, allow-listed tools -> NO approval gate.
Write tools are deliberately NOT here; they must go through the approval gate.
"""

from __future__ import annotations

import structlog

from buildpolaris_ai.platform.mcp.read_tools_impl import (
    answer_question_impl,
    enrich_context_impl,
    search_knowledge_impl,
)

logger = structlog.get_logger()


def _load_fastmcp():
    """Try known FastMCP import paths.

    The MCP Python SDK has moved FastMCP between versions.
    This keeps the gateway/orchestrator resilient while we verify the exact package layout.
    """
    try:
        from mcp.server.fastmcp import FastMCP

        return FastMCP
    except ModuleNotFoundError:
        pass

    try:
        from mcp.server.fastmcp.server import FastMCP

        return FastMCP
    except ModuleNotFoundError:
        pass

    try:
        from fastmcp import FastMCP

        return FastMCP
    except ModuleNotFoundError:
        pass

    return None


FastMCP = _load_fastmcp()
mcp = None

if FastMCP is not None:
    mcp = FastMCP("buildpolaris-knowledge")

    @mcp.tool()
    async def search_knowledge(question: str, tenant_id: str, limit: int = 3) -> list[dict]:
        """Semantic search over the tenant's knowledge base (read-only)."""
        return await search_knowledge_impl(question, tenant_id, limit)

    @mcp.tool()
    async def enrich_context(docnames: list[str], tenant_id: str, limit: int = 3) -> list[dict]:
        """Graph enrichment: documents related to the given seeds (read-only)."""
        return await enrich_context_impl(docnames, tenant_id, limit)

    @mcp.tool()
    async def answer_question(question: str, tenant_id: str) -> dict:
        """Full hybrid RAG answer with validated citations (read-only)."""
        return await answer_question_impl(question, tenant_id)

else:
    logger.warning(
        "FastMCP is not available; MCP stdio server disabled. "
        "Orchestrator read tools still work through read_tools_impl."
    )


if __name__ == "__main__":
    if mcp is None:
        raise SystemExit(
            "FastMCP is not available. Inspect the installed mcp package layout "
            "before running the MCP stdio server."
        )

    # Local dev over stdio. Production should use HTTP transport with real auth.
    mcp.run(transport="stdio")
