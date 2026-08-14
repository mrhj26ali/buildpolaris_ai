"""v1 Actions endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from buildpolaris_ai.gateway.middleware.tenant_auth import get_user_context
from buildpolaris_ai.platform.schemas import UserContext

import structlog

logger = structlog.get_logger()
router = APIRouter(tags=["v1 Actions"])


@router.post("/actions/propose")
async def propose_action(
    user_ctx: UserContext = Depends(get_user_context),
):
    """Internal: agents propose writes via BFF Client (FR-8.6)."""
    return {
        "status": "info",
        "message": "Write proposals are handled via BFF Client in agent handlers (FR-8.6)",
    }
