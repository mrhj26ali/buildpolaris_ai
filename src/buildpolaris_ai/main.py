# src/buildpolaris_ai/main.py
"""FastAPI application entry point for buildpolaris_ai.
Handles dependency injection for the Hexagonal adapters."""
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import uuid4

import structlog
from fastapi import FastAPI, Depends

from buildpolaris_ai.platform.bff_client import BFFClientProtocol
from buildpolaris_ai.platform.bff_mock import MockBFFClient
from buildpolaris_ai.platform.schemas import ActionApprovalGate, GateStatus, UserContext
from buildpolaris_ai.gateway.api import llm_test
from buildpolaris_ai.gateway.api import copilot_test

# Configure structlog for production-grade JSON logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() # Use structlog.processors.JSONRenderer() in prod
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False
)
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("buildpolaris_ai starting up...")
    # Startup logic: init DB connections, load models, etc.
    yield
    logger.info("buildpolaris_ai shutting down...")
    # Shutdown logic

app = FastAPI(
    title="BuildPolaris AI Sidecar",
    description="Event-driven AI sidecar for the BuildPolaris Construction PM Platform",
    version="0.1.0",
    lifespan=lifespan
)

app.include_router(llm_test.router)
app.include_router(copilot_test.router)

# --- Dependency Injection ---
# In production, this will return the real HttpBFFClient. 
# For now, it returns the Mock. This is the ONLY place we change it.
def get_bff_client() -> BFFClientProtocol:
    # TODO: Swap to HttpBFFClient() when BFF is ready
    return MockBFFClient()

# --- Health Check ---
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "service": "buildpolaris_ai"}

# --- Gateway Endpoint (Test Contract) ---
@app.post("/gateway/test-rfi-draft", tags=["Gateway"])
async def test_rfi_draft(
    bff_client: BFFClientProtocol = Depends(get_bff_client)
):
    """
    Temporary endpoint to test the BFF client contract and approval gate flow.
    Will be replaced by the actual LangGraph agent router.
    """
    # 1. Simulate User Context (Usually passed via JWT from PWA -> BFF -> AI)
    user_ctx = UserContext(
        user_id="user-123",
        tenant_id="tenant-abc",
        company_id="company-xyz",
        assigned_project_ids=["proj-001"],
        role="Project Manager"
    )

    # 2. Simulate Agent proposing a write action (Drafting an RFI)
    proposed_gate = ActionApprovalGate(
        ref_doctype="RFI",
        proposed_payload={
            "subject": "Clarification on concrete mix design",
            "cost_impact": False,
            "schedule_impact": True
        },
        model_version="claude-3-5-sonnet-20260801",
        confidence_score=0.92,
        tool_trace_id=str(uuid4())
    )

    # 3. Submit to BFF (Mock)
    gate_id = await bff_client.submit_approval_gate(proposed_gate, user_ctx)
    
    # 4. Check status (Mock auto-approves for dev flow)
    status = await bff_client.check_gate_status(gate_id)
    
    # 5. Execute if approved
    result = {}
    if status == GateStatus.APPROVED:
        result = await bff_client.execute_approved_gate(gate_id)

    return {
        "gate_id": gate_id,
        "status": status.value,
        "execution_result": result
    }