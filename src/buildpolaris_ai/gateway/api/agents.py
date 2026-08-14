"""Agents endpoint: list available agent capabilities."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from buildpolaris_ai.gateway.orchestrator.agent_registry import get_agent_registry

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("")
async def list_agents(role: Optional[str] = None):
    """List registered agents.

    If a role is supplied, agents that declare allowed_roles are filtered.
    Role enforcement remains server-side in the BFF/ERPNext boundary.
    """
    registry = get_agent_registry()
    manifests = registry.list_manifests()

    if role:
        manifests = [
            manifest
            for manifest in manifests
            if not manifest.allowed_roles or role in manifest.allowed_roles
        ]

    return {
        "items": [manifest.model_dump() for manifest in manifests],
        "total": len(manifests),
    }
