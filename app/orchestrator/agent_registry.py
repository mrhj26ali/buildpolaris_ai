"""AgentRegistry â€” the microkernel's registration seam (ARCH Â§3.3).

Discovers every agents/<name>/manifest.yaml at startup, validates its
shape, and maps `agent_type` -> the agent's `run()` entrypoint. Adding a
new agent is: drop a new folder under app/agents/ with a manifest.yaml
and a handler.py exposing `async def run(context) -> AgentResult`, and
this registry picks it up on next startup â€” no orchestrator code changes.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.exceptions import UnknownAgentTypeError
from app.observability.logging import get_logger
from app.orchestrator.contracts import AgentModule

logger = get_logger(__name__)

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"


@dataclass(slots=True)
class AgentManifest:
    agent_type: str
    display_name: str
    description: str
    target_doctype: str
    intent_examples: list[str]
    module_path: str


class AgentRegistry:
    def __init__(self) -> None:
        self._manifests: dict[str, AgentManifest] = {}
        self._modules: dict[str, AgentModule] = {}

    def discover(self) -> None:
        if not AGENTS_DIR.exists():
            logger.warning("agents_dir_missing", path=str(AGENTS_DIR))
            return

        for folder in sorted(AGENTS_DIR.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue  # _template/ is a scaffold, never registered
            manifest_path = folder / "manifest.yaml"
            if not manifest_path.exists():
                continue

            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            agent_type = raw["agent_type"]
            module_path = f"app.agents.{folder.name}.handler"

            self._manifests[agent_type] = AgentManifest(
                agent_type=agent_type,
                display_name=raw.get("display_name", agent_type),
                description=raw.get("description", ""),
                target_doctype=raw["target_doctype"],
                intent_examples=raw.get("intent_examples", []),
                module_path=module_path,
            )

            module = importlib.import_module(module_path)
            self._modules[agent_type] = module
            logger.info("agent_registered", agent_type=agent_type, module=module_path)

    def get_module(self, agent_type: str) -> AgentModule:
        module = self._modules.get(agent_type)
        if module is None:
            raise UnknownAgentTypeError(agent_type)
        return module

    def get_manifest(self, agent_type: str) -> AgentManifest:
        manifest = self._manifests.get(agent_type)
        if manifest is None:
            raise UnknownAgentTypeError(agent_type)
        return manifest

    def all_manifests(self) -> list[AgentManifest]:
        return list(self._manifests.values())

    def match_intent(self, message: str) -> str | None:
        """Very small keyword-overlap matcher used as intent_classifier's
        fallback when the LLM-based classification is ambiguous â€” real
        classification lives in orchestrator/intent_classifier.py; this is
        just registry-side lookup support so the classifier doesn't need
        its own copy of every agent's intent_examples."""
        message_lower = message.lower()
        for manifest in self._manifests.values():
            for example in manifest.intent_examples:
                if example.lower() in message_lower:
                    return manifest.agent_type
        return None


@lru_cache
def get_agent_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.discover()
    return registry
