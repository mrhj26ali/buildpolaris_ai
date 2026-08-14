"""BFFClient â€” general-purpose authenticated REST client for calls this
sidecar makes back into buildpolaris_bff (ARCH Â§4.2 Direction 2). Used
directly for simple one-shot calls (e.g. resolving a signed download URL
during ingestion is instead passed IN by the BFF, so in practice this
client's main consumer is mcp_client.py's transport â€” kept as its own
module so a non-MCP BFF endpoint can also be called without inventing a
second HTTP client).
"""
from __future__ import annotations

import httpx

from app.config import get_settings
from app.observability.logging import get_logger
from app.observability.tracing import get_trace_id

logger = get_logger(__name__)


class BFFClient:
    def __init__(self, raw_scope_assertion_token: str | None = None) -> None:
        self._settings = get_settings().bff
        self._raw_assertion = raw_scope_assertion_token

    def _headers(self) -> dict[str, str]:
        headers = {
            "X-Service-Key": self._settings.service_key.get_secret_value(),
            "X-Trace-Id": get_trace_id(),
        }
        if self._raw_assertion:
            headers["X-Scope-Assertion"] = self._raw_assertion
        return headers

    async def post(self, path: str, json: dict) -> dict:
        url = f"{self._settings.base_url}{path}"
        async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
            response = await client.post(url, json=json, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._settings.base_url}{path}"
        async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
            response = await client.get(url, params=params, headers=self._headers())
            response.raise_for_status()
            return response.json()
