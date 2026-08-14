"""Canonical error envelope and domain exceptions."""
from __future__ import annotations

from typing import Any
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger()

class BuildPolarisError(Exception):
    """Base exception for all domain errors."""
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

class UnauthorizedError(BuildPolarisError):
    def __init__(self, message: str = "Authentication required.", details: dict[str, Any] | None = None):
        super().__init__(code="UNAUTHORIZED", message=message, status_code=401, details=details)

class ForbiddenError(BuildPolarisError):
    def __init__(self, message: str = "Insufficient permissions.", details: dict[str, Any] | None = None):
        super().__init__(code="FORBIDDEN", message=message, status_code=403, details=details)

class NotFoundError(BuildPolarisError):
    def __init__(self, message: str = "Resource not found.", details: dict[str, Any] | None = None):
        super().__init__(code="NOT_FOUND", message=message, status_code=404, details=details)

class ConflictError(BuildPolarisError):
    def __init__(self, message: str = "Conflict.", details: dict[str, Any] | None = None):
        super().__init__(code="CONFLICT", message=message, status_code=409, details=details)

class ValidationError(BuildPolarisError):
    def __init__(self, message: str = "Validation failed.", details: dict[str, Any] | None = None):
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=422, details=details)

class RateLimitError(BuildPolarisError):
    def __init__(self, message: str = "Rate limit exceeded.", details: dict[str, Any] | None = None):
        super().__init__(code="RATE_LIMITED", message=message, status_code=429, details=details)

async def buildpolaris_exception_handler(request: Request, exc: BuildPolarisError) -> JSONResponse:
    """Formats domain exceptions into the canonical error envelope."""
    request_id = getattr(request.state, "request_id", None)
    
    payload = {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": request_id,
        }
    }
    
    logger.warning(
        "Domain error handled",
        request_id=request_id,
        error_code=exc.code,
        status_code=exc.status_code,
        path=request.url.path,
    )
    
    headers = {}
    if request_id:
        headers["X-Request-ID"] = request_id
        
    return JSONResponse(
        status_code=exc.status_code,
        content=payload,
        headers=headers,
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Maps FastAPI validation errors into the canonical envelope."""
    request_id = getattr(request.state, "request_id", None)
    errors = exc.errors()
    
    payload = {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "details": {"fields": errors},
            "request_id": request_id,
        }
    }
    
    headers = {"X-Request-ID": request_id} if request_id else {}
    return JSONResponse(status_code=422, content=payload, headers=headers)

async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions to prevent stack trace leakage."""
    request_id = getattr(request.state, "request_id", None)
    
    logger.error(
        "Unhandled exception",
        request_id=request_id,
        exc_info=True,
        path=request.url.path,
    )
    
    payload = {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
            "details": {},
            "request_id": request_id,
        }
    }
    
    headers = {"X-Request-ID": request_id} if request_id else {}
    return JSONResponse(status_code=500, content=payload, headers=headers)