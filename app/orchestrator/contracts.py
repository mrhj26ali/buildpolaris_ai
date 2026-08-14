"""The AgentModule contract every agents/<name>/handler.py implements
(ARCH Â§3.3: "adding an agent = new folder + registry entry, never
touching the orchestrator"). This is the microkernel's one extension
point.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.orchestrator.context import TurnContext
from app.platform.governance.proposal_schema import ProposedAction


@dataclass(slots=True)
class AgentResult:
    proposed_action: ProposedAction
    rationale: str  # short human-readable summary shown alongside the pending-approval card


@runtime_checkable
class AgentModule(Protocol):
    """Every agent module exposes exactly this shape. The orchestrator
    calls `run()` and does nothing else â€” it never inspects an agent's
    internals, imports its prompts, or knows what target DocType it
    writes to (that's declared in the agent's own manifest.yaml and
    enforced by governance/payload_verifier.py, not by the orchestrator).
    """

    async def run(self, context: TurnContext) -> AgentResult: ...
