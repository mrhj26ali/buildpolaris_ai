"""FastAPI application entry point for buildpolaris_ai."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from buildpolaris_ai.gateway.api import health
from buildpolaris_ai.gateway.api.v1.router import v1_router
from buildpolaris_ai.platform.errors import (
    BuildPolarisError,
    buildpolaris_exception_handler,
    validation_exception_handler,
    generic_exception_handler,
)
from fastapi.exceptions import RequestValidationError

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("buildpolaris_ai starting up...")
    yield
    logger.info("buildpolaris_ai shutting down...")


app = FastAPI(
    title="BuildPolaris AI Sidecar",
    description="Event-driven AI sidecar for the BuildPolaris Construction PM Platform",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Error handlers
app.add_exception_handler(BuildPolarisError, buildpolaris_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Mount routes
app.include_router(v1_router)
app.include_router(health.router)


@app.get("/", tags=["System"])
async def root():
    return {
        "service": "buildpolaris_ai",
        "status": "running",
        "version": "2.0.0",
        "phase": "Full Implementation — RAG Fusion + Multi-Agent + Free LLM APIs",
    }


def run():
    """Entry point for `buildpolaris-ai` CLI command."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    run()
