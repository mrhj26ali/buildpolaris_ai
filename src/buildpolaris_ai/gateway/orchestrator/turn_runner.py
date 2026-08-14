"""LangGraph turn runner: classify -> route -> execute."""
from __future__ import annotations

from typing import Any, Optional, TypedDict

import structlog
from langgraph.graph import END, StateGraph

from buildpolaris_ai.gateway.orchestrator.agent_registry import (
    AgentRegistry, get_agent_registry,
)
from buildpolaris_ai.gateway.orchestrator.schemas import (
    AgentInvocation, AgentResult, ChatTurn,
)
from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.model_provider import get_model_provider
from buildpolaris_ai.platform.retrieval.citation_validator import CitationValidator
from buildpolaris_ai.platform.retrieval.rag_service import RagService
from buildpolaris_ai.platform.schemas import UserContext
from buildpolaris_ai.platform.security.prompt_guard import PromptInjectionGuard

logger = structlog.get_logger()


class TurnState(TypedDict, total=False):
    turn: Any
    tenant_id: str
    user_context: Any
    route: str
    tool: Optional[str]
    tool_args: dict
    agent_id: Optional[str]
    result: Any


class TurnRunner:
    """Runs one chat turn through the orchestration graph."""

    def __init__(self, conn: Any, registry: AgentRegistry | None = None) -> None:
        self.conn = conn
        self.registry = registry or get_agent_registry()
        self.settings = get_settings()
        self.prompt_guard = PromptInjectionGuard()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(TurnState)
        graph.add_node("classify", self.classify)
        graph.add_node("run_rag", self.run_rag)
        graph.add_node("run_read_tool", self.run_read_tool)
        graph.add_node("run_agent", self.run_agent)
        graph.add_node("route_error", self.route_error)
        graph.set_entry_point("classify")
        graph.add_conditional_edges(
            "classify", self._choose_route,
            {"rag": "run_rag", "read_tool": "run_read_tool", "agent": "run_agent", "error": "route_error"},
        )
        graph.add_edge("run_rag", END)
        graph.add_edge("run_read_tool", END)
        graph.add_edge("run_agent", END)
        graph.add_edge("route_error", END)
        return graph.compile()

    def _choose_route(self, state: TurnState) -> str:
        route = state.get("route", "error")
        return route if route in {"rag", "read_tool", "agent"} else "error"

    async def run(self, turn: ChatTurn, tenant_id: str, user_context: UserContext | None = None) -> AgentResult:
        resolved_ctx = user_context or turn.user_context or UserContext(
            user_id="anonymous", tenant_id=tenant_id, company_id="default",
            assigned_project_ids=[], role="Viewer",
        )
        state: TurnState = {"turn": turn, "tenant_id": tenant_id, "user_context": resolved_ctx}
        final_state = await self.graph.ainvoke(state)
        result = final_state.get("result")
        if result is None:
            return AgentResult(kind="error", error="Turn runner produced no result.")
        return result

    async def classify(self, state: TurnState) -> dict:
        turn: ChatTurn | None = state.get("turn")
        if turn is None:
            return {"route": "error", "result": AgentResult(kind="error", error="Missing turn payload.")}

        # Prompt injection check on user input
        sanitized_msg, was_flagged = self.prompt_guard.filter_user_input(turn.message)
        turn.message = sanitized_msg

        route = turn.route or "auto"
        agent_id = turn.agent_id
        tool = turn.tool

        if route == "auto":
            if tool:
                route = "read_tool"
            else:
                triggered = self.registry.find_by_trigger(turn.message)
                if triggered:
                    route = "agent"
                    agent_id = triggered.manifest.id
                else:
                    route = "rag"

        if route == "agent" and not agent_id:
            triggered = self.registry.find_by_trigger(turn.message)
            if triggered:
                agent_id = triggered.manifest.id

        if route not in {"rag", "read_tool", "agent"}:
            return {"route": "error", "result": AgentResult(kind="error", error=f"Unsupported route: {route}")}

        return {"route": route, "agent_id": agent_id, "tool": tool, "tool_args": turn.tool_args or {}}

    async def run_rag(self, state: TurnState) -> dict:
        turn: ChatTurn = state.get("turn")
        tenant_id: str = state.get("tenant_id", "TENANT-ALPHA")
        try:
            if self.conn is None:
                raise RuntimeError("Database connection unavailable for RAG.")

            provider = get_model_provider()
            settings = self.settings
            validator = CitationValidator(jaccard_threshold=settings.rag.jaccard_threshold)
            service = RagService(
                conn=self.conn,
                provider=provider,
                validator=validator,
                vector_limit=settings.rag.vector_search_limit,
                graph_limit=settings.rag.graph_enrich_limit,
                max_retries=settings.rag.max_generation_retries,
                use_rag_fusion=settings.rag.use_rag_fusion,
                use_query_transform=settings.rag.use_query_transform,
                rerank_top_k=settings.rag.rerank_top_k,
            )
            rag_answer = await service.answer(turn.message, tenant_id)
            return {
                "result": AgentResult(
                    kind="answer",
                    answer=rag_answer.answer,
                    citations=rag_answer.citations,
                    citations_validated=rag_answer.citations_validated,
                    attempts=rag_answer.attempts,
                )
            }
        except Exception as exc:
            logger.error("RAG turn failed", error=str(exc))
            return {"result": AgentResult(kind="error", error=str(exc))}

    async def run_read_tool(self, state: TurnState) -> dict:
        turn: ChatTurn = state.get("turn")
        tenant_id: str = state.get("tenant_id", "TENANT-ALPHA")
        tool = state.get("tool") or turn.tool or "search_knowledge"
        tool_args = state.get("tool_args") or turn.tool_args or {}

        try:
            from buildpolaris_ai.platform.mcp.read_tools_impl import (
                search_knowledge_impl, enrich_context_impl, answer_question_impl,
            )
            if tool == "search_knowledge":
                output = await search_knowledge_impl(
                    question=tool_args.get("question") or turn.message,
                    tenant_id=tenant_id,
                    limit=int(tool_args.get("limit", 3)),
                )
            elif tool == "enrich_context":
                docnames = tool_args.get("docnames") or []
                if isinstance(docnames, str):
                    docnames = [docnames]
                output = await enrich_context_impl(docnames=docnames, tenant_id=tenant_id)
            elif tool == "answer_question":
                output = await answer_question_impl(question=tool_args.get("question") or turn.message, tenant_id=tenant_id)
            else:
                return {"result": AgentResult(kind="error", error=f"Unsupported tool: {tool}")}

            return {"result": AgentResult(kind="read_tool", tool_name=tool, tool_result=output)}
        except Exception as exc:
            logger.error("Read tool failed", tool=tool, error=str(exc))
            return {"result": AgentResult(kind="error", error=str(exc))}

    async def run_agent(self, state: TurnState) -> dict:
        turn: ChatTurn = state.get("turn")
        tenant_id: str = state.get("tenant_id", "TENANT-ALPHA")
        user_context: UserContext = state.get("user_context")
        agent_id = state.get("agent_id") or turn.agent_id

        try:
            if not agent_id:
                return {"result": AgentResult(kind="error", error="No agent_id provided.")}
            agent = self.registry.get(agent_id)
            if agent is None:
                return {"result": AgentResult(kind="error", error=f"Agent '{agent_id}' not registered.")}

            invocation = AgentInvocation(
                agent_id=agent.manifest.id,
                message=turn.message,
                tenant_id=tenant_id,
                user_context=user_context,
                args=turn.tool_args or {},
            )
            result = await agent.handler(invocation)
            return {"result": result}
        except Exception as exc:
            logger.error("Agent turn failed", agent_id=agent_id, error=str(exc))
            return {"result": AgentResult(kind="error", error=str(exc))}

    async def route_error(self, state: TurnState) -> dict:
        result = state.get("result") or AgentResult(kind="error", error="Unsupported turn route.")
        return {"result": result}
