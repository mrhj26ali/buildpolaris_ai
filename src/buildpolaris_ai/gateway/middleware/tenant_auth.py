"""Auth dependency: extracts UserContext from JWT."""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from buildpolaris_ai.platform.auth.jwt_handler import JWTHandler
from buildpolaris_ai.platform.schemas import UserContext

_jwt_handler = JWTHandler()


async def get_user_context(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> UserContext:
    """Extract UserContext from BFF JWT or fallback header."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]  # Strip "Bearer "
        user_ctx = await _jwt_handler.verify_and_decode(token)
        if user_ctx:
            return user_ctx

    # Dev fallback
    if x_tenant_id:
        return UserContext(
            user_id="dev-user",
            tenant_id=x_tenant_id,
            company_id="dev-company",
            assigned_project_ids=["PROJ-DEV"],
            role="Admin",
        )

    raise HTTPException(status_code=401, detail="Missing or invalid authentication")


def get_dev_token(tenant_id: str = "TENANT-ALPHA") -> str:
    """Helper for testing."""
    return f"mock-jwt-{tenant_id}"
