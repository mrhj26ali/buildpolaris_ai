"""BFFClient -- general-purpose authenticated REST client for calls this
sidecar makes back into buildpolaris_bff (ARCH v2.1 Direction 2).

buildpolaris_bff is a Frappe app. Frappe treats any request that doesn't
carry a valid session cookie or an `Authorization: token key:secret`
header as an anonymous Guest -- there is no other transport-identity
mechanism, and BFF's own permission checks (`_assert_service_caller()` in
mcp_server.py, and the AI-service-account check on
`propose_agent_action`) reject Guests outright. So every outbound call
this client makes carries that header, using the credentials
buildpolaris_bff/install.py generated for the low-privilege
'BuildPolaris AI Service' account (see app/config.py's BFFClientSettings
docstring for where those come from).

The Scope Assertion is a separate, narrower concept (see
gateway/auth/scope_assertion.py) and is passed as an explicit
`scope_assertion` field in the JSON body/query params -- never a custom
header -- because that's exactly what BFF's whitelisted methods
(`propose_agent_action`, `mcp_server.call_tool`) declare as a keyword
argument. A Frappe whitelisted method only sees kwargs bound from the
request body/query string; it does not inspect arbitrary custom headers
unless it explicitly calls frappe.get_request_header(), which these
don't.
"""
from __future__ import annotations

import httpx

from app.config import get_settings
from app.exceptions import BuildPolarisAIError
from app.observability.logging import get_logger
from app.observability.tracing import get_trace_id

logger = get_logger(__name__)


class BFFCallError(BuildPolarisAIError):
    """Raised when a call into buildpolaris_bff fails outright (network,
    non-2xx, or a well-formed BuildPolaris error envelope)."""


class BFFClient:
    """One instance is safe to reuse across calls -- it carries no
    per-turn state itself (unlike BFFMCPClient, which pins a single
    Scope Assertion for one copilot turn)."""

    def __init__(self) -> None:
        self._settings = get_settings().bff

    @property
    def settings(self):
        return self._settings

    def _headers(self) -> dict[str, str]:
        api_key = self._settings.api_key.get_secret_value()
        api_secret = self._settings.api_secret.get_secret_value()
        headers = {"X-Trace-Id": get_trace_id()}
        if api_key and api_secret:
            headers["Authorization"] = f"token {api_key}:{api_secret}"
        else:
            logger.warning(
                "bff_client_missing_credentials",
                detail="BFF__API_KEY/BFF__API_SECRET not configured -- "
                "this call will be treated as an anonymous Guest by buildpolaris_bff "
                "and rejected.",
            )
        return headers

    @staticmethod
    def _unwrap(payload: dict) -> dict:
        """Frappe wraps every whitelisted-method return value as
        {"message": <value>}. BuildPolaris's own envelope on top of that
        is {"success": bool, "data": ..., "message": ..., "error_code": ...}
        (buildpolaris_bff/shared/api_envelope.py). Unwrap both layers so
        callers just get the real payload."""
        inner = payload.get("message", payload)
        if isinstance(inner, dict) and "success" in inner:
            if not inner.get("success"):
                raise BFFCallError(inner.get("message") or "buildpolaris_bff returned an error")
            return inner.get("data") or {}
        return inner

    async def post(self, path: str, json: dict) -> dict:
        url = f"{self._settings.base_url.rstrip('/')}{path}"
        async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
            try:
                response = await client.post(url, json=json, headers=self._headers())
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error("bff_call_failed", path=path, status=exc.response.status_code)
                raise BFFCallError(f"buildpolaris_bff POST {path} -> {exc.response.status_code}") from exc
            except httpx.HTTPError as exc:
                logger.error("bff_call_unreachable", path=path, error=str(exc))
                raise BFFCallError(f"buildpolaris_bff unreachable: {exc}") from exc
            return self._unwrap(response.json())

    async def get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._settings.base_url.rstrip('/')}{path}"
        async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
            try:
                response = await client.get(url, params=params, headers=self._headers())
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error("bff_call_failed", path=path, status=exc.response.status_code)
                raise BFFCallError(f"buildpolaris_bff GET {path} -> {exc.response.status_code}") from exc
            except httpx.HTTPError as exc:
                logger.error("bff_call_unreachable", path=path, error=str(exc))
                raise BFFCallError(f"buildpolaris_bff unreachable: {exc}") from exc
            return self._unwrap(response.json())
