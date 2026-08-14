"""Health endpoints: liveness, readiness, AI availability."""
from __future__ import annotations

import asyncio
from typing import Any

import redis.asyncio as redis
import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from buildpolaris_ai.platform.config import get_settings
from buildpolaris_ai.platform.retrieval.connection import create_ai_connection

logger = structlog.get_logger()
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "buildpolaris_ai", "version": "2.0.0"}


@router.get("/health/live")
async def health_live():
    return {"status": "alive", "service": "buildpolaris_ai"}


async def _check_database(timeout: float = 3.0) -> dict[str, Any]:
    try:
        conn = await asyncio.wait_for(create_ai_connection(), timeout=timeout)
        await asyncio.wait_for(conn.execute("SELECT 1"), timeout=timeout)
        await conn.close()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


async def _check_redis(timeout: float = 2.0) -> dict[str, Any]:
    settings = get_settings()
    try:
        client = redis.from_url(settings.redis.url, decode_responses=True)
        await asyncio.wait_for(client.ping(), timeout=timeout)
        await client.aclose()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@router.get("/health/ready")
async def health_ready():
    settings = get_settings()
    database = await _check_database()
    redis_check = await _check_redis()
    ready = database["status"] == "ok" and redis_check["status"] == "ok"

    payload = {
        "status": "ready" if ready else "degraded",
        "service": "buildpolaris_ai",
        "checks": {"database": database, "redis": redis_check},
        "ai_gateway": {
            "available": ready,
            "model_provider": settings.model_provider.primary_provider,
            "embedding_provider": settings.embedding.provider,
        },
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)
