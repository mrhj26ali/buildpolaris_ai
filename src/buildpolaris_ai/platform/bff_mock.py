# src/buildpolaris_ai/platform/bff_mock.py
"""
Mock implementation of BFFClientProtocol for local development.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from buildpolaris_ai.platform.schemas import ActionApprovalGate, GateStatus, UserContext
from buildpolaris_ai.platform.bff_client import BFFClientProtocol

logger = logging.getLogger(__name__)

class MockBFFClient:
    """
    Mock implementation of BFFClientProtocol for development/testing.
    Simulates the BFF behavior without making actual HTTP requests.
    """
    
    def __init__(self):
        self._gates = {}
        self._auto_approve = True  # Set to False to test pending/rejected flows
        logger.info("MockBFFClient initialized (auto_approve=%s)", self._auto_approve)
    
    async def submit_approval_gate(self, gate: ActionApprovalGate, user_ctx: UserContext) -> str:
        """Submit a gate for approval (mock implementation)."""
        gate_id = f"gate_{uuid.uuid4().hex[:8]}"
        
        # Store the gate
        self._gates[gate_id] = {
            "gate": gate,
            "user_ctx": user_ctx,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        
        logger.info(f"Mock: Submitted approval gate {gate_id} for action: {gate.ref_doctype}")
        
        # Auto-approve for development flow
        if self._auto_approve:
            self._gates[gate_id]["status"] = "approved"
            logger.info(f"Mock: Auto-approved gate {gate_id}")
        
        return gate_id
    
    async def check_gate_status(self, gate_id: str) -> GateStatus:
        """Check the status of a gate (mock implementation)."""
        if gate_id not in self._gates:
            logger.warning(f"Mock: Gate {gate_id} not found")
            return GateStatus.REJECTED  # Default to rejected if not found
        
        gate_data = self._gates[gate_id]
        status_str = gate_data["status"]
        
        # Map string status to enum
        status_map = {
            "pending": GateStatus.PENDING,
            "approved": GateStatus.APPROVED,
            "rejected": GateStatus.REJECTED,
        }
        
        return status_map.get(status_str, GateStatus.REJECTED)
    
    async def execute_approved_gate(self, gate_id: str) -> dict:
        """Execute an approved gate (mock implementation)."""
        if gate_id not in self._gates:
            raise ValueError(f"Gate {gate_id} not found")
        
        gate_data = self._gates[gate_id]
        
        if gate_data["status"] != "approved":
            raise ValueError(f"Gate {gate_id} is not approved (status: {gate_data['status']})")
        
        # Execute the gate
        gate_data["status"] = "executed"
        gate_data["executed_at"] = datetime.now().isoformat()
        
        logger.info(f"Mock: Executed gate {gate_id}")
        
        # Return a realistic mock response
        return {
            "success": True,
            "gate_id": gate_id,
            "message": f"Mock execution of {gate_data['gate'].ref_doctype} completed",
            "data": {
                "docname": f"RFI-{uuid.uuid4().hex[:6].upper()}",
                "status": "Drafted",
                "created_by": gate_data['user_ctx'].user_id
            },
        }
    
    # Optional: Method to manually control auto-approve behavior
    def set_auto_approve(self, enabled: bool):
        """Toggle auto-approval for testing different flows."""
        self._auto_approve = enabled
        logger.info(f"Mock: Auto-approve set to {enabled}")