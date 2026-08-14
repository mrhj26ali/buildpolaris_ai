"""NFR-AIGOV.1 spend/usage surface + NFR-OBS.3 request counters. Guarded
by the service credential (this is an internal, BFF-facing surface, not
something exposed to the PWA directly â€” the BFF's own admin screen calls
this and re-renders it for a Company Admin).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.gateway.auth.service_credential import verify_service_credential
from app.observability.metrics import counters
from app.observability.token_usage import get_token_usage_tracker

router = APIRouter(
    prefix="/metrics", tags=["metrics"], dependencies=[Depends(verify_service_credential)]
)


@router.get("")
async def get_metrics() -> dict:
    return {"counters": counters.snapshot()}


@router.get("/usage/{company}")
async def get_tenant_usage(company: str) -> dict:
    return get_token_usage_tracker().snapshot(company)


@router.get("/usage")
async def get_all_usage() -> dict:
    return {"tenants": get_token_usage_tracker().all_snapshots()}
