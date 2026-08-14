# src/buildpolaris_ai/platform/bff_client.py
"""
Hexagonal Port for communicating with buildpolaris_bff.
We use typing.Protocol for structural subtyping (duck typing).
"""
from __future__ import annotations

import logging
import uuid
from typing import Protocol, runtime_checkable

import httpx
from buildpolaris_ai.platform.schemas import (
    ActionApprovalGate, GateStatus, PaginatedResponse, UserContext,
)

logger = logging.getLogger(__name__)


class BFFServiceError(Exception):
    """Normalized error thrown for HTTP BFF client failures."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"BFF {status_code}: {message}")


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

    async def list_documents(
        self,
        doctype: str,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        """Paginated document listing from the BFF."""
        ...


class HttpBFFClient(BFFClientProtocol):
    """HTTP implementation of BFFClientProtocol for buildpolaris_bff integration."""

    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(timeout_seconds),
        )
        self._gate_cache: dict[str, ActionApprovalGate] = {}

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("HTTP request to BFF failed", method=method, path=path, error=str(exc))
            raise BFFServiceError(500, str(exc)) from exc

        if response.status_code >= 400:
            message = response.text or response.reason_phrase
            logger.warning("BFF returned error", status=response.status_code, path=path, text=message)
            raise BFFServiceError(response.status_code, message)

        return response

    async def submit_approval_gate(self, gate: ActionApprovalGate, user_ctx: UserContext) -> str:
        response = await self._request(
            "POST",
            "/api/v1/approval-gates",
            json={
                "gate": gate.model_dump(),
                "user_context": user_ctx.model_dump(),
            },
        )
        payload = response.json()
        gate_id = payload.get("gate_id")
        if not gate_id:
            raise BFFServiceError(500, "Missing gate_id in BFF response")
        self._gate_cache[gate_id] = gate
        return gate_id

    async def check_gate_status(self, gate_id: str) -> GateStatus:
        response = await self._request("GET", f"/api/v1/approval-gates/{gate_id}/status")
        payload = response.json()
        return GateStatus(payload.get("status", GateStatus.REJECTED.value))

    async def execute_approved_gate(self, gate_id: str) -> dict:
        gate = self._gate_cache.get(gate_id)
        if gate is None:
            raise ValueError(f"Unknown gate_id {gate_id}")

        response = await self._request(
            "POST",
            "/api/v1/agent-writes",
            json={
                "gate_id": gate_id,
                "action_type": f"create_{gate.ref_doctype.lower()}",
                "payload": gate.proposed_payload,
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        return response.json()

    async def list_documents(
        self,
        doctype: str,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        response = await self._request(
            "GET",
            "/api/v1/documents",
            params={
                "doctype": doctype,
                "tenant_id": tenant_id,
                "page": page,
                "page_size": page_size,
            },
        )
        return PaginatedResponse(**response.json())
