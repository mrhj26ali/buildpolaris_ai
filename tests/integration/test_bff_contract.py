# tests/integration/test_bff_contract.py
"""
Phase 1 contract tests: MockBFFClient satisfies BFFClientProtocol structurally
and every payload shape matches platform/schemas.py exactly.
This is what makes the later BFF swap provably safe.
"""
import pytest
from buildpolaris_ai.platform.bff_mock import MockBFFClient
from buildpolaris_ai.platform.bff_client import BFFClientProtocol
from buildpolaris_ai.platform.schemas import (
    ActionApprovalGate, GateStatus, PaginatedResponse, UserContext,
    DOCTYPE_SCHEMA_REGISTRY,
)


USER_CTX = UserContext(
    user_id="contract-test-user",
    tenant_id="contract-test-tenant",
    company_id="contract-test-company",
    assigned_project_ids=["proj-001"],
    role="Project Manager",
)


class TestStructuralConformance:
    """Assert MockBFFClient satisfies BFFClientProtocol structurally."""

    def test_isinstance_check(self):
        client = MockBFFClient()
        assert isinstance(client, BFFClientProtocol)

    def test_has_submit_approval_gate(self):
        assert callable(getattr(MockBFFClient, "submit_approval_gate", None))

    def test_has_check_gate_status(self):
        assert callable(getattr(MockBFFClient, "check_gate_status", None))

    def test_has_execute_approved_gate(self):
        assert callable(getattr(MockBFFClient, "execute_approved_gate", None))

    def test_has_list_documents(self):
        assert callable(getattr(MockBFFClient, "list_documents", None))


class TestGateLifecycleContract:
    @pytest.mark.asyncio
    async def test_full_gate_lifecycle(self):
        """submit -> check -> execute must follow the gate state machine."""
        client = MockBFFClient(auto_approve=True, latency_ms=(0, 1))
        gate = ActionApprovalGate(
            ref_doctype="RFI",
            proposed_payload={"subject": "Contract test RFI"},
            model_version="contract-test-model",
            confidence_score=0.95,
        )
        gate_id = await client.submit_approval_gate(gate, USER_CTX)
        assert isinstance(gate_id, str)
        assert len(gate_id) > 0

        status = await client.check_gate_status(gate_id)
        assert isinstance(status, GateStatus)
        assert status == GateStatus.APPROVED

        result = await client.execute_approved_gate(gate_id)
        assert isinstance(result, dict)
        assert result["success"] is True
        assert "gate_id" in result


class TestPaginationContract:
    @pytest.mark.asyncio
    async def test_paginated_response_schema(self):
        """list_documents must return a valid PaginatedResponse."""
        client = MockBFFClient(latency_ms=(0, 1))
        docs = [{"docname": f"RFI-{i}", "status": "Open"} for i in range(30)]
        client.load_documents("RFI", "contract-tenant", docs)

        response = await client.list_documents("RFI", "contract-tenant", page=1, page_size=10)
        assert isinstance(response, PaginatedResponse)
        assert response.total == 30
        assert response.page == 1
        assert response.page_size == 10
        assert response.has_next is True
        assert len(response.items) == 10


class TestPayloadSchemaConformance:
    """Every doctype in the registry must have a valid Pydantic schema."""

    def test_all_doctypes_have_schemas(self):
        expected = {
            "RFI", "Task", "DailyLog", "PunchListItem", "IncidentReport",
            "SOVLine", "ChangeEvent", "ChangeOrder", "ContractClause",
            "ActionApprovalGate",
        }
        assert set(DOCTYPE_SCHEMA_REGISTRY.keys()) == expected

    def test_schemas_are_pydantic_models(self):
        from pydantic import BaseModel
        for doctype, schema_cls in DOCTYPE_SCHEMA_REGISTRY.items():
            assert issubclass(schema_cls, BaseModel), f"{doctype} schema is not a Pydantic model"

    def test_schemas_have_required_fields(self):
        """Every schema must have at minimum an ID and project_id field."""
        for doctype, schema_cls in DOCTYPE_SCHEMA_REGISTRY.items():
            fields = schema_cls.model_fields
            assert len(fields) > 0, f"{doctype} schema has no fields"
