"""Structured request logging + trace_id propagation middleware
(NFR-OBS.1). Reads the inbound trace_id set by the PWA/job origin and
forwarded by buildpolaris_bff; mints one only if genuinely absent (a
direct/dev-tool call, never expected from the real BFF proxy path).
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.observability.logging import get_logger
from app.observability.tracing import new_trace_id, trace_id_var

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or new_trace_id()
        token = trace_id_var.set(trace_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed", path=request.url.path, method=request.method
            )
            raise
        finally:
            trace_id_var.reset(token)

        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "request_completed",
            path=request.url.path,
            method=request.method,
            status_code=getattr(response, "status_code", None),
            duration_ms=round(duration_ms, 2),
            trace_id=trace_id,
        )
        response.headers["X-Trace-Id"] = trace_id
        return response
