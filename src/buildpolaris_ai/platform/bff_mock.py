# src/buildpolaris_ai/platform/bff_mock.py
"""
Hardened mock implementation of BFFClientProtocol for local development.
Phase 1: realistic latency simulation, pagination, configurable failure-injection
(timeouts, 4xx/5xx) so Phase 6 resilience tests have something real to exercise.
"""
import asyncio
import logging
import random
import uuid
from datetime import datetime
from typing import Optional

from buildpolaris_ai.platform.schemas import (
    ActionApprovalGate, GateStatus, PaginatedResponse, UserContext,
)
from buildpolaris_ai.platform.bff_client import BFFClientProtocol

logger = logging.getLogger(__name__)


class BFFServiceError(Exception):
    """Simulated BFF service error with HTTP-like status code."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"BFF {status_code}: {message}")


class MockBFFClient:
    """
    Hardened mock of BFFClientProtocol for development and testing.

    Configurable behavior:
    - auto_approve: auto-approve gates (default True for dev flow)
    - latency_ms: (min, max) simulated latency range
    - failure_rate: probability of a 500 error (0.0-1.0)
    - timeout_rate: probability of a timeout (0.0-1.0)
    - error_4xx_rate: probability of a 400/403/404 error (0.0-1.0)
    """

    def __init__(
        self,
        auto_approve: bool = True,
        latency_ms: tuple[int, int] = (50, 200),
        failure_rate: float = 0.0,
        timeout_rate: float = 0.0,
        error_4xx_rate: float = 0.0,
    ):
        self._gates: dict[str, dict] = {}
        self._documents: dict[str, list[dict]] = {}
        self._auto_approve = auto_approve
        self._latency_min = latency_ms[0]
        self._latency_max = latency_ms[1]
        self._failure_rate = failure_rate
        self._timeout_rate = timeout_rate
        self._error_4xx_rate = error_4xx_rate
        logger.info(
            "MockBFFClient initialized (auto_approve=%s, latency=%s, failure=%.2f, timeout=%.2f)",
            auto_approve, latency_ms, failure_rate, timeout_rate,
        )

    # ------------------------------------------------------------------
    # Simulation helpers
    # ------------------------------------------------------------------

    async def _simulate_latency(self) -> None:
        delay = random.uniform(self._latency_min, self._latency_max) / 1000.0
        await asyncio.sleep(delay)

    async def _maybe_fail(self) -> None:
        if random.random() < self._timeout_rate:
            raise asyncio.TimeoutError("Simulated BFF timeout")
        if random.random() < self._failure_rate:
            raise BFFServiceError(500, "Simulated BFF internal error")
        if random.random() < self._error_4xx_rate:
            code = random.choice([400, 403, 404])
            raise BFFServiceError(code, f"Simulated BFF {code} error")

    # ------------------------------------------------------------------
    # BFFClientProtocol implementation
    # ------------------------------------------------------------------

    async def submit_approval_gate(self, gate: ActionApprovalGate, user_ctx: UserContext) -> str:
        await self._simulate_latency()
        await self._maybe_fail()

        gate_id = f"gate_{uuid.uuid4().hex[:8]}"
        self._gates[gate_id] = {
            "gate": gate,
            "user_ctx": user_ctx,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        logger.info("Mock: Submitted approval gate %s for %s", gate_id, gate.ref_doctype)

        if self._auto_approve:
            self._gates[gate_id]["status"] = "approved"
            logger.info("Mock: Auto-approved gate %s", gate_id)
        return gate_id

    async def check_gate_status(self, gate_id: str) -> GateStatus:
        await self._simulate_latency()
        await self._maybe_fail()

        if gate_id not in self._gates:
            logger.warning("Mock: Gate %s not found", gate_id)
            return GateStatus.REJECTED
        status_map = {
            "pending": GateStatus.PENDING,
            "approved": GateStatus.APPROVED,
            "rejected": GateStatus.REJECTED,
        }
        return status_map.get(self._gates[gate_id]["status"], GateStatus.REJECTED)

    async def execute_approved_gate(self, gate_id: str) -> dict:
        await self._simulate_latency()
        await self._maybe_fail()

        if gate_id not in self._gates:
            raise ValueError(f"Gate {gate_id} not found")
        gate_data = self._gates[gate_id]
        if gate_data["status"] != "approved":
            raise ValueError(f"Gate {gate_id} is not approved (status: {gate_data['status']})")

        gate_data["status"] = "executed"
        gate_data["executed_at"] = datetime.now().isoformat()
        logger.info("Mock: Executed gate %s", gate_id)
        return {
            "success": True,
            "gate_id": gate_id,
            "message": f"Mock execution of {gate_data['gate'].ref_doctype} completed",
            "data": {
                "docname": f"RFI-{uuid.uuid4().hex[:6].upper()}",
                "status": "Drafted",
                "created_by": gate_data["user_ctx"].user_id,
            },
        }

    # ------------------------------------------------------------------
    # Pagination support (Phase 1)
    # ------------------------------------------------------------------

    async def list_documents(
        self,
        doctype: str,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        """Paginated document listing from the mock BFF."""
        await self._simulate_latency()
        await self._maybe_fail()

        all_docs = self._documents.get(f"{tenant_id}:{doctype}", [])
        total = len(all_docs)
        start = (page - 1) * page_size
        end = start + page_size
        items = all_docs[start:end]
        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=end < total,
        )

    def load_documents(self, doctype: str, tenant_id: str, docs: list[dict]) -> None:
        """Load mock documents for pagination testing."""
        key = f"{tenant_id}:{doctype}"
        self._documents[key] = docs

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def set_auto_approve(self, enabled: bool) -> None:
        self._auto_approve = enabled
        logger.info("Mock: Auto-approve set to %s", enabled)

    def set_failure_rate(self, rate: float) -> None:
        self._failure_rate = rate

    def set_timeout_rate(self, rate: float) -> None:
        self._timeout_rate = rate

    def set_latency(self, min_ms: int, max_ms: int) -> None:
        self._latency_min = min_ms
        self._latency_max = max_ms
