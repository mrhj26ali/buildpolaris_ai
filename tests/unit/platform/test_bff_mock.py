# tests/unit/platform/test_bff_mock.py
"""Unit tests for the hardened MockBFFClient."""
import asyncio
import pytest
from buildpolaris_ai.platform.bff_mock import MockBFFClient, BFFServiceError
from buildpolaris_ai.platform.bff_client import BFFClientProtocol
from buildpolaris_ai.platform.schemas import (
    ActionApprovalGate, GateStatus, PaginatedResponse, UserContext,
)

USER_CTX = UserContext(
    user_id="test-user",
    tenant_id="test-tenant",
    company_id="test-company",
    assigned_project_ids=["proj-001"],
    role="Project Manager",
)

GATE = ActionApprovalGate(
    ref_doctype="RFI",
    proposed_payload={"subject": "Test RFI"},
    model_version="test-model",
    confidence_score=0.9,
)


class TestProtocolConformance:
    def test_mock_satisfies_protocol(self):
        client = MockBFFClient()
        assert isinstance(client, BFFClientProtocol)

    def test_has_list_documents(self):
        assert callable(getattr(MockBFFClient, "list_documents", None))


class TestApprovalGateFlow:
    @pytest.mark.asyncio
    async def test_submit_and_auto_approve(self):
        client = MockBFFClient(auto_approve=True, latency_ms=(0, 1))
        gate_id = await client.submit_approval_gate(GATE, USER_CTX)
        assert gate_id.startswith("gate_")
        status = await client.check_gate_status(gate_id)
        assert status == GateStatus.APPROVED

    @pytest.mark.asyncio
    async def test_submit_no_auto_approve_stays_pending(self):
        client = MockBFFClient(auto_approve=False, latency_ms=(0, 1))
        gate_id = await client.submit_approval_gate(GATE, USER_CTX)
        status = await client.check_gate_status(gate_id)
        assert status == GateStatus.PENDING

    @pytest.mark.asyncio
    async def test_execute_approved_gate(self):
        client = MockBFFClient(auto_approve=True, latency_ms=(0, 1))
        gate_id = await client.submit_approval_gate(GATE, USER_CTX)
        result = await client.execute_approved_gate(gate_id)
        assert result["success"] is True
        assert result["gate_id"] == gate_id

    @pytest.mark.asyncio
    async def test_execute_pending_gate_raises(self):
        client = MockBFFClient(auto_approve=False, latency_ms=(0, 1))
        gate_id = await client.submit_approval_gate(GATE, USER_CTX)
        with pytest.raises(ValueError, match="not approved"):
            await client.execute_approved_gate(gate_id)

    @pytest.mark.asyncio
    async def test_unknown_gate_returns_rejected(self):
        client = MockBFFClient(latency_ms=(0, 1))
        status = await client.check_gate_status("gate_nonexistent")
        assert status == GateStatus.REJECTED


class TestPagination:
    @pytest.mark.asyncio
    async def test_paginated_listing(self):
        client = MockBFFClient(latency_ms=(0, 1))
        docs = [{"docname": f"RFI-{i}"} for i in range(50)]
        client.load_documents("RFI", "tenant-a", docs)

        page1 = await client.list_documents("RFI", "tenant-a", page=1, page_size=20)
        assert len(page1.items) == 20
        assert page1.total == 50
        assert page1.has_next is True

        page3 = await client.list_documents("RFI", "tenant-a", page=3, page_size=20)
        assert len(page3.items) == 10
        assert page3.has_next is False

    @pytest.mark.asyncio
    async def test_empty_listing(self):
        client = MockBFFClient(latency_ms=(0, 1))
        page = await client.list_documents("RFI", "tenant-empty", page=1)
        assert page.total == 0
        assert page.items == []

    @pytest.mark.asyncio
    async def test_returns_paginated_response_type(self):
        client = MockBFFClient(latency_ms=(0, 1))
        page = await client.list_documents("RFI", "tenant-x", page=1)
        assert isinstance(page, PaginatedResponse)


class TestFailureInjection:
    @pytest.mark.asyncio
    async def test_failure_rate_100_raises(self):
        client = MockBFFClient(latency_ms=(0, 1), failure_rate=1.0)
        with pytest.raises(BFFServiceError) as exc_info:
            await client.submit_approval_gate(GATE, USER_CTX)
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_timeout_rate_100_raises(self):
        client = MockBFFClient(latency_ms=(0, 1), timeout_rate=1.0)
        with pytest.raises(asyncio.TimeoutError):
            await client.submit_approval_gate(GATE, USER_CTX)

    @pytest.mark.asyncio
    async def test_zero_failure_rate_succeeds(self):
        client = MockBFFClient(latency_ms=(0, 1), failure_rate=0.0, timeout_rate=0.0)
        gate_id = await client.submit_approval_gate(GATE, USER_CTX)
        assert gate_id.startswith("gate_")
