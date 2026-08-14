"""Token and request governance per tenant (NFR-AIGOV.1, NFR-AIGOV.2)."""
from __future__ import annotations

from functools import lru_cache

import redis.asyncio as redis
import structlog

from buildpolaris_ai.platform.config import get_settings

logger = structlog.get_logger()


class TokenGovernor:
    """Tracks and enforces per-tenant token/request budgets."""

    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client
        self.settings = get_settings().governance

    def _token_key(self, tenant_id: str) -> str:
        return f"bp.governance.tokens.{tenant_id}"

    def _request_key(self, tenant_id: str) -> str:
        return f"bp.governance.requests.{tenant_id}"

    async def record_usage(self, tenant_id: str, tokens: int) -> None:
        """Record token usage for a tenant."""
        await self.redis.incrby(self._token_key(tenant_id), tokens)
        await self.redis.incr(self._request_key(tenant_id))

    async def check_budget(self, tenant_id: str) -> tuple[bool, str]:
        """Check if tenant is within budget. Returns (allowed, reason)."""
        token_count = await self.redis.get(self._token_key(tenant_id))
        token_count = int(token_count) if token_count else 0

        request_count = await self.redis.get(self._request_key(tenant_id))
        request_count = int(request_count) if request_count else 0

        if token_count >= self.settings.token_hard_ceiling_per_tenant:
            return False, "Token hard ceiling reached"

        if request_count >= self.settings.request_soft_ceiling_per_tenant:
            logger.warning("Tenant request soft ceiling reached", tenant_id=tenant_id)
            # Soft ceiling: alert but don't block yet
            return True, "Request soft ceiling reached (warning)"

        if token_count >= self.settings.token_soft_ceiling_per_tenant:
            logger.warning("Tenant token soft ceiling reached", tenant_id=tenant_id)
            return True, "Token soft ceiling reached (warning)"

        return True, "OK"

    async def get_usage(self, tenant_id: str) -> dict:
        """Get current usage stats for a tenant."""
        token_count = await self.redis.get(self._token_key(tenant_id))
        request_count = await self.redis.get(self._request_key(tenant_id))
        return {
            "tenant_id": tenant_id,
            "tokens_used": int(token_count) if token_count else 0,
            "requests_made": int(request_count) if request_count else 0,
            "token_ceiling": self.settings.token_hard_ceiling_per_tenant,
            "request_ceiling": self.settings.request_soft_ceiling_per_tenant,
        }
