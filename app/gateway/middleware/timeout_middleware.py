"""Per-request timeout â€” backs NFR-PERF.6's latency budget and, combined
with the circuit breaker, NFR-SCALE.5 ("the platform must remain fully
usable for all non-AI workflows if buildpolaris_ai is slow or
unreachable" â€” this is the sidecar's own half of failing fast rather than
hanging the BFF's request thread indefinitely).
"""
from __future__ import annotations

import asyncio

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.observability.logging import get_logger

logger = get_logger(__name__)

# SSE streaming responses (copilot/message) manage their own internal
# per-stage timeouts and must not be wrapped here â€” a blanket timeout
# would kill a legitimately long-lived stream.
EXEMPT_PATH_PREFIXES = ("/copilot/message",)


class TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, timeout_seconds: float = 30.0) -> None:
        super().__init__(app)
        self._timeout = timeout_seconds

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in EXEMPT_PATH_PREFIXES):
            return await call_next(request)

        try:
            return await asyncio.wait_for(call_next(request), timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.error("request_timeout", path=request.url.path, timeout_s=self._timeout)
            return JSONResponse(
                status_code=504,
                content={"detail": "buildpolaris_ai timed out processing this request"},
            )
