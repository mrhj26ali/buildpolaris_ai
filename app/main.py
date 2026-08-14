"""buildpolaris_ai â€” FastAPI sidecar entrypoint.

Wires: middleware stack (request logging -> timeout -> circuit breaker),
every gateway router, exception handlers mapping every app.exceptions
type to a correct HTTP status, and startup/shutdown for the Postgres
pool + agent registry discovery.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db.postgres import close_pool, init_pool
from app.exceptions import (
    ApprovalProposalError,
    BuildPolarisAIError,
    CitationValidationExhaustedError,
    InvalidScopeAssertionError,
    InvalidServiceCredentialError,
    ModelProviderUnavailableError,
    NoExtractableTextError,
    ScopeMismatchError,
    UnknownAgentTypeError,
)
from app.gateway.middleware.circuit_breaker_middleware import CircuitBreakerMiddleware
from app.gateway.middleware.request_logging import RequestLoggingMiddleware
from app.gateway.middleware.timeout_middleware import TimeoutMiddleware
from app.gateway.routers import copilot_message, graph_sync, health, ingest, metrics
from app.observability.logging import configure_logging, get_logger
from app.orchestrator.agent_registry import get_agent_registry

configure_logging()
logger = get_logger(__name__)

_EXCEPTION_STATUS_MAP: dict[type[Exception], int] = {
    InvalidServiceCredentialError: 401,
    InvalidScopeAssertionError: 401,
    ScopeMismatchError: 403,
    UnknownAgentTypeError: 400,
    CitationValidationExhaustedError: 422,
    NoExtractableTextError: 422,
    ModelProviderUnavailableError: 503,
    ApprovalProposalError: 502,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    get_agent_registry()  # discover + register every agents/<name>/manifest.yaml on startup
    logger.info("buildpolaris_ai_startup_complete")
    yield
    await close_pool()
    logger.info("buildpolaris_ai_shutdown_complete")


app = FastAPI(
    title="buildpolaris_ai",
    description="BuildPolaris AI sidecar â€” hexagonal microkernel over a derived retrieval platform.",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(CircuitBreakerMiddleware)
app.add_middleware(
    TimeoutMiddleware, timeout_seconds=get_settings().resilience.provider_timeout_seconds
)
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(BuildPolarisAIError)
async def handle_buildpolaris_ai_error(request: Request, exc: BuildPolarisAIError):
    status_code = _EXCEPTION_STATUS_MAP.get(type(exc), 400)
    logger.warning(
        "buildpolaris_ai_error", error_type=type(exc).__name__, detail=str(exc), path=request.url.path
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc), "error": type(exc).__name__})


app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(copilot_message.router)
app.include_router(ingest.router)
app.include_router(graph_sync.router)


if get_settings().app.enable_dev_routes:
    from app.gateway.auth.scope_assertion import mint_scope_assertion

    @app.get("/dev/mint-scope-assertion")
    async def dev_mint_scope_assertion(
        company: str = "dev-co", project: str = "dev-project", user: str = "dev@buildpolaris.local",
        role: str = "Project Manager",
    ) -> dict:
        """Dev-only helper â€” mints a Scope Assertion locally so the sidecar's
        test suite and manual curl/Postman sessions don't require a live BFF.
        Registered only when APP__ENABLE_DEV_ROUTES=true."""
        token = mint_scope_assertion(company, project, user, role)
        return {"scope_assertion": token}
