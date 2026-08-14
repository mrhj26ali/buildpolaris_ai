"""Master v1 Router."""
from fastapi import APIRouter

from buildpolaris_ai.gateway.api.v1.copilot import router as copilot_router
from buildpolaris_ai.gateway.api.v1.actions import router as actions_router
from buildpolaris_ai.gateway.api.v1.ingest import router as ingest_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(copilot_router)
v1_router.include_router(actions_router)
v1_router.include_router(ingest_router)
