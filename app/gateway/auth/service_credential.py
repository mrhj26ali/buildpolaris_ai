"""ARCH v2.1 Â§4.2 Direction 1 â€” service credential check.

`buildpolaris_ai` is never exposed to the public internet directly; every
path to it goes through `buildpolaris_bff`. This is the first of the two
checks every inbound call must pass: a simple X-Service-Key bearer header,
appropriate because this is a private-network call, not a public API
(ARCH explicitly rejects building the full external-facing OAuth 2.1
resource-server flow for a surface with exactly one internal consumer).
"""
from __future__ import annotations

import hmac

from fastapi import Header

from app.config import get_settings
from app.exceptions import InvalidServiceCredentialError


def verify_service_credential(x_service_key: str = Header(...)) -> None:
    settings = get_settings().service_auth
    expected = settings.service_key.get_secret_value()
    if not hmac.compare_digest(x_service_key, expected):
        raise InvalidServiceCredentialError("invalid X-Service-Key")
