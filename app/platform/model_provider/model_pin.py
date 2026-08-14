"""NFR-AIGOV.2 â€” model-version pinning per tenant or globally.

"A silent upstream model update cannot change agent behavior (approval-
gate reliability, citation accuracy) without a deliberate, tested
rollout." This resolves, for a given company (tenant), the model_version
string every ModelProviderAdapter call should be pinned to â€” global
default from config, overridable per tenant via the same store used for
other tenant-level configuration (kept in-process + Postgres-backed here;
swappable without touching callers since everything routes through
resolve_model_version()).
"""
from __future__ import annotations

from app.config import get_settings

# In-memory tenant override map. A production deployment would back this
# with a small Postgres table (tenant_model_pins) written by an admin
# screen; the resolution contract below is what matters for NFR-AIGOV.2,
# not the storage medium, and is the one seam a persistence swap touches.
_tenant_overrides: dict[str, str] = {}


def set_tenant_model_pin(company: str, model_version: str) -> None:
    _tenant_overrides[company] = model_version


def clear_tenant_model_pin(company: str) -> None:
    _tenant_overrides.pop(company, None)


def resolve_model_version(company: str | None = None) -> str:
    if company and company in _tenant_overrides:
        return _tenant_overrides[company]
    return get_settings().model_provider.model_version_pin
