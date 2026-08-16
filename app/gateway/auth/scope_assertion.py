"""ARCH v2.1 Â§4.2 Direction 1 â€” the Scope Assertion.

A small, signed, short-lived payload minted by
`buildpolaris_bff/shared/scope_assertion.py` at request time, containing
`{company, project, user, role, expires_at}` with a ~60-second TTL. It
lets this sidecar enforce "the tool call inherits the calling user's
tenant/Project permission scope at the query layer" (NFR-SEC.8) without a
round-trip back to MariaDB on every retrieval query.

It is NOT a general-purpose auth token and is never sent to the browser.
A stolen or replayed assertion is limited by its short TTL and by the
fact that it can only ever narrow scope â€” the BFF only mints one after its
own has_permission check has already passed, so this can never grant a
permission the acting user's Role doesn't already have.

HMAC-SHA256 signed, symmetric secret shared with the BFF
(SERVICE_AUTH__SCOPE_ASSERTION_SECRET on both sides) â€” both services are
first-party and internal-network-only (ARCH Â§4.4), so asymmetric signing
isn't earning its complexity here.

WIRE FORMAT (must match buildpolaris_bff/shared/scope_assertion.py
EXACTLY â€” that module is the reference implementation):

    token = base64url(json_bytes) + "." + base64url(hmac_sha256(secret, json_bytes))

The signature is computed over the RAW JSON BYTES, before base64
encoding â€” NOT over the base64-encoded string. Signing the base64 string
instead of the underlying bytes is a distinct (and incompatible) byte
sequence; a previous version of this file made exactly that mistake and
every assertion minted by the BFF failed verification here as a result.

Role: the BFF mints `role` as the full list of the asserted user's Frappe
Roles (`frappe.get_roles(user)`), not a single string â€” this module
mirrors that as `role: list[str]`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import Header

from app.config import get_settings
from app.exceptions import InvalidScopeAssertionError


@dataclass(slots=True, frozen=True)
class ScopeAssertion:
    company: str | None
    project: str | None
    user: str
    role: list[str]
    expires_at: int

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    def has_role(self, *roles: str) -> bool:
        return any(r in self.role for r in roles)


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_scope_assertion(
    company: str | None, project: str | None, user: str, role: list[str] | str,
    ttl_seconds: int | None = None,
) -> str:
    """Used by tests/dev tooling only. Production Scope Assertions are
    minted by buildpolaris_bff (buildpolaris_bff/shared/scope_assertion.py);
    this sidecar carries a mirror so its own test suite and local dev
    scripts don't need a live BFF just to exercise an authenticated call
    chain. MUST stay byte-for-byte compatible with the BFF's minter."""
    settings = get_settings().service_auth
    ttl = ttl_seconds or settings.scope_assertion_max_ttl_seconds
    role_list = [role] if isinstance(role, str) else list(role)
    payload = {
        "company": company,
        "project": project,
        "user": user,
        "role": role_list,
        "expires_at": int(time.time()) + ttl,
    }
    # Sign the RAW JSON BYTES (sort_keys to match BFF's json.dumps(..., sort_keys=True)).
    body_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    secret = settings.scope_assertion_secret.get_secret_value().encode()
    signature = hmac.new(secret, body_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(body_bytes)}.{_b64url_encode(signature)}"


def _verify(token: str) -> ScopeAssertion:
    settings = get_settings().service_auth
    try:
        body_b64, sig_b64 = token.split(".", 1)
        body_bytes = _b64url_decode(body_b64)
        signature = _b64url_decode(sig_b64)
    except Exception as exc:
        raise InvalidScopeAssertionError("malformed scope assertion") from exc

    secret = settings.scope_assertion_secret.get_secret_value().encode()
    # Verify over the RAW JSON BYTES â€” same bytes the BFF signed, not the
    # base64 string. This is the line that was previously wrong.
    expected_sig = hmac.new(secret, body_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_sig):
        raise InvalidScopeAssertionError("scope assertion signature mismatch")

    try:
        payload = json.loads(body_bytes)
        role = payload.get("role") or []
        if isinstance(role, str):
            role = [role]
        assertion = ScopeAssertion(
            company=payload.get("company"),
            project=payload.get("project"),
            user=payload["user"],
            role=role,
            expires_at=int(payload["expires_at"]),
        )
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidScopeAssertionError("scope assertion payload malformed") from exc

    if assertion.is_expired():
        raise InvalidScopeAssertionError("scope assertion expired")

    # Defensive belt-and-suspenders on top of the TTL embedded in the
    # payload: never trust an assertion whose *issued* lifetime exceeds
    # the sidecar's own configured max, even if the signature is valid.
    if assertion.expires_at - int(time.time()) > settings.scope_assertion_max_ttl_seconds + 5:
        raise InvalidScopeAssertionError("scope assertion TTL exceeds configured maximum")

    return assertion


def verify_scope_assertion(x_scope_assertion: str = Header(...)) -> ScopeAssertion:
    """FastAPI dependency â€” reads the assertion from the X-Scope-Assertion
    header, used by every inbound router (copilot_message, ingest,
    graph_sync)."""
    return _verify(x_scope_assertion)


def verify_scope_assertion_str(token: str) -> ScopeAssertion:
    """Same verification, callable directly with a raw token string â€”
    kept for symmetry/testing where the assertion isn't sourced from a
    FastAPI Header dependency."""
    return _verify(token)
