# src/buildpolaris_ai/platform/bff_client.py
"""
Hexagonal Port for communicating with buildpolaris_bff.
We use typing.Protocol for structural subtyping (duck typing).
"""
import logging
from typing import Protocol, runtime_checkable

from buildpolaris_ai.platform.schemas import ActionApprovalGate, GateStatus, UserContext

logger = logging.getLogger(__name__)

@runtime_checkable
class BFFClientProtocol(Protocol):
    """
    The strict contract for interacting with the BFF.
    buildpolaris_ai holds NO ERPNext credentials. It only holds credentials 
    scoped to the BFF's api/agent_writes.py.
    """
    
    async def submit_approval_gate(self, gate: ActionApprovalGate, user_ctx: UserContext) -> str:
        """Submits a proposed write action to the BFF for human approval. Returns gate_id."""
        ...

    async def check_gate_status(self, gate_id: str) -> GateStatus:
        """Checks if a human has approved/rejected a pending gate."""
        ...

    async def execute_approved_gate(self, gate_id: str) -> dict:
        """Tells the BFF to execute the mutation now that it's approved."""
        ...