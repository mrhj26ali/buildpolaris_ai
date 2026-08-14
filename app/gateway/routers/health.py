"""Health + circuit-breaker status. No auth required â€” this is what a
container orchestrator's liveness probe hits, and NFR-OBS.3's "status
endpoint" for a human checking whether the sidecar itself is up (distinct
from metrics.py's per-tenant spend/usage view).
"""
from __future__ import annotations

from fastapi import APIRouter

from app.platform.model_provider.circuit_breaker import get_circuit_breaker

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": "buildpolaris_ai"}


@router.get("/healthz/providers")
async def provider_health() -> dict:
    breaker = get_circuit_breaker()
    return {"providers": breaker.snapshot(), "all_open": breaker.all_providers_open()}
