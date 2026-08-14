"""Factory for choosing the active BFF client implementation.

Phase A defaults to MockBFFClient.
Phase B will add HttpBFFClient and make this environment-driven.
"""

from __future__ import annotations

from buildpolaris_ai.platform.bff_client import BFFClientProtocol, HttpBFFClient
from buildpolaris_ai.platform.bff_mock import MockBFFClient
from buildpolaris_ai.platform.config import get_settings


def get_bff_client() -> BFFClientProtocol:
    """Return the active BFF client based on settings."""
    settings = get_settings()

    if settings.bff.mode == "http":
        if not settings.bff.base_url or not settings.bff.api_token:
            raise ValueError("HTTP BFF mode requires bff.base_url and bff.api_token")

        return HttpBFFClient(
            base_url=settings.bff.base_url,
            api_token=settings.bff.api_token.get_secret_value(),
            timeout_seconds=settings.bff.timeout_seconds,
        )

    # Phase A: pending approvals must remain pending.
    # Do not auto-approve proposed writes in the gateway/orchestrator path.
    return MockBFFClient(auto_approve=False)
