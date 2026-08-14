"""Agent registry.

Agents self-register by existing as folders under buildpolaris_ai/agents
with a manifest.yaml and a handler.py exposing `handle`.

New agent = new folder. No orchestrator code changes required.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable, Literal

import structlog
import yaml
from pydantic import BaseModel, Field

from buildpolaris_ai.gateway.orchestrator.schemas import AgentInvocation, AgentResult

logger = structlog.get_logger()


class AgentManifest(BaseModel):
    """Manifest schema for an agent plugin."""

    id: str
    name: str
    description: str = ""
    risk_tier: Literal["read", "write_gated", "write_autonomous_never"] = "read"
    budget_class: str = "standard"
    model_preference: str | None = None
    triggers: list[str] = Field(default_factory=list)
    allowed_roles: list[str] = Field(default_factory=list)
    module: str | None = None


@dataclass
class RegisteredAgent:
    """A loaded agent plugin: manifest + async handler."""

    manifest: AgentManifest
    handler: Callable[[AgentInvocation], Awaitable[AgentResult]]


class AgentRegistry:
    """Registry that loads and resolves agent plugins."""

    def __init__(self) -> None:
        self._agents: dict[str, RegisteredAgent] = {}

    @property
    def agents_root(self) -> Path:
        return Path(__file__).resolve().parents[2] / "agents"

    def load_from_disk(self) -> None:
        """Discover agent folders and load their manifests/handlers."""
        self._agents = {}

        if not self.agents_root.exists():
            logger.warning("Agents root does not exist", path=str(self.agents_root))
            return

        for child in sorted(self.agents_root.iterdir()):
            if not child.is_dir():
                continue

            manifest_path = child / "manifest.yaml"
            if not manifest_path.exists():
                continue

            try:
                raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
                if "id" not in raw:
                    raw["id"] = child.name

                manifest = AgentManifest(**raw)
                module_name = manifest.module or f"buildpolaris_ai.agents.{manifest.id}.handler"
                module = importlib.import_module(module_name)
                handler = getattr(module, "handle")

                self._agents[manifest.id] = RegisteredAgent(
                    manifest=manifest,
                    handler=handler,
                )

                logger.info("Loaded agent plugin", agent_id=manifest.id, module=module_name)
            except Exception as exc:
                logger.warning("Skipping agent folder", folder=str(child), error=str(exc))

    def list_manifests(self) -> list[AgentManifest]:
        """Return manifests for all loaded agents."""
        return [agent.manifest for agent in self._agents.values()]

    def get(self, agent_id: str) -> RegisteredAgent | None:
        """Return a loaded agent by id."""
        return self._agents.get(agent_id)

    def find_by_trigger(self, text: str) -> RegisteredAgent | None:
        """Return the first agent whose trigger phrase appears in the text."""
        needle = (text or "").lower()

        for agent in self._agents.values():
            for trigger in agent.manifest.triggers:
                if trigger.lower() in needle:
                    return agent

        return None


@lru_cache
def get_agent_registry() -> AgentRegistry:
    """Cached registry singleton."""
    registry = AgentRegistry()
    registry.load_from_disk()
    return registry
