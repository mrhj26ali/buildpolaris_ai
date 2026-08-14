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
    company: str
    project: str | None
    user: str
    role: str
    expires_at: int

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_scope_assertion(
    company: str, project: str | None, user: str, role: str, ttl_seconds: int | None = None
) -> str:
    """Used by tests/dev tooling and by BFF-side mirrors of this module.
    Production Scope Assertions are minted by buildpolaris_bff, but the
    sidecar carries this so its own test suite and local dev scripts don't
    need a live BFF just to exercise an authenticated call chain."""
    settings = get_settings().service_auth
    ttl = ttl_seconds or settings.scope_assertion_max_ttl_seconds
    payload = {
        "company": company,
        "project": project,
        "user": user,
        "role": role,
        "expires_at": int(time.time()) + ttl,
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    secret = settings.scope_assertion_secret.get_secret_value().encode()
    signature = _b64url_encode(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_scope_assertion(x_scope_assertion: str = Header(...)) -> ScopeAssertion:
    settings = get_settings().service_auth
    try:
        body, signature = x_scope_assertion.split(".", 1)
    except ValueError as exc:
        raise InvalidScopeAssertionError("malformed scope assertion") from exc

    secret = settings.scope_assertion_secret.get_secret_value().encode()
    expected_sig = _b64url_encode(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected_sig):
        raise InvalidScopeAssertionError("scope assertion signature mismatch")

    try:
        payload = json.loads(_b64url_decode(body))
        assertion = ScopeAssertion(
            company=payload["company"],
            project=payload.get("project"),
            user=payload["user"],
            role=payload["role"],
            expires_at=int(payload["expires_at"]),
        )
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidScopeAssertionError("scope assertion payload malformed") from exc

    if assertion.is_expired():
        raise InvalidScopeAssertionError("scope assertion expired")

    # Defensive belt-and-suspenders on top of the TTL embedded in the
    # payload: never trust an assertion whose *issued* lifetime exceeds
    # the sidecar's own configured max, even if the signature is valid.
    if assertion.expires_at - int(time.time()) > settings.scope_assertion_max_ttl_seconds:
        raise InvalidScopeAssertionError("scope assertion TTL exceeds configured maximum")

    return assertion
