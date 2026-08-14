"""TurnContext â€” everything an agent or the RAG path needs for one
copilot turn, threaded through explicitly rather than via globals so
concurrent turns (different tenants, different users) never leak state
into each other.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.gateway.auth.scope_assertion import ScopeAssertion
from app.platform.bff.mcp_client import BFFMCPClient
from app.platform.model_provider.adapter import ModelProviderAdapter


@dataclass(slots=True)
class TurnContext:
    thread_id: str
    message: str
    history: list[dict]
    assertion: ScopeAssertion
    raw_assertion_token: str
    trace_id: str
    model_provider: ModelProviderAdapter
    mcp_client: BFFMCPClient
    extra: dict = field(default_factory=dict)  # agent-specific scratch space (e.g. attached file refs)

    @property
    def company(self) -> str:
        return self.assertion.company

    @property
    def project(self) -> str | None:
        return self.assertion.project

    @property
    def user(self) -> str:
        return self.assertion.user
