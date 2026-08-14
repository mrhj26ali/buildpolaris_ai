"""Gateway-level circuit breaker state exposure.

The actual breaker logic that matters (falling back from a rate-limited
model provider to a secondary one) lives in
platform/model_provider/circuit_breaker.py â€” that is a per-provider
concern, not a per-HTTP-request one. This middleware's job is narrower:
if the *model provider* breaker is currently open (all providers down),
fail fast on provider-dependent routes with a clear 503 rather than
letting the request proceed into a guaranteed timeout, which is what
actually protects NFR-SCALE.5 at the BFF's calling layer.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.observability.logging import get_logger
from app.platform.model_provider.circuit_breaker import get_circuit_breaker

logger = get_logger(__name__)

PROVIDER_DEPENDENT_PATH_PREFIXES = ("/copilot/message", "/copilot/agent", "/ingest")


class CircuitBreakerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in PROVIDER_DEPENDENT_PATH_PREFIXES):
            breaker = get_circuit_breaker()
            if breaker.all_providers_open():
                logger.warning("circuit_breaker_all_open_fail_fast", path=path)
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "All configured model providers are currently "
                        "unavailable. This does not affect non-AI platform "
                        "functions (NFR-SCALE.5)."
                    },
                )
        return await call_next(request)
