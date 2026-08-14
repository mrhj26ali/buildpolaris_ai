"""Template handler â€” copy to app/agents/<new_agent_name>/handler.py and
implement `run()`. Every agent module must expose exactly this signature
(app/orchestrator/contracts.py's AgentModule protocol) â€” the orchestrator
calls nothing else on it.
"""
from __future__ import annotations

from app.agents.base import build_proposed_action
from app.orchestrator.context import TurnContext
from app.orchestrator.contracts import AgentResult


async def run(context: TurnContext) -> AgentResult:
    # 1. Gather whatever input this agent needs (context.message,
    #    context.extra, and/or an MCP read-tool call via context.mcp_client).
    # 2. Call context.model_provider.structured_complete(...) with a
    #    Pydantic schema matching the target DocType's draftable fields.
    # 3. Assemble a ProposedAction via build_proposed_action() â€” never
    #    apply anything directly; this handler never writes to BFF itself.
    raise NotImplementedError("copy this template and implement run()")
