"""ARCH v2.1 Â§4.2 Direction 2 â€” AI calls BFF's MCP surface, on-behalf-of.

When this sidecar calls back into the BFF (a read-only MCP tool call, per
UC-8.2), it authenticates as itself (its own service credential) but
forwards the Scope Assertion it was handed for the current turn. The
BFF's has_permission check, when the tool call arrives, runs against the
*asserted user*, not against the AI service account's own permissions â€”
the AI service account itself has no direct Role-based access to any
BuildPolaris data; it is purely a transport identity.
"""
from __future__ import annotations

from app.gateway.auth.scope_assertion import ScopeAssertion


def build_on_behalf_of_headers(
    assertion: ScopeAssertion, ai_service_key: str, raw_assertion_token: str
) -> dict[str, str]:
    """Headers this sidecar attaches to an outbound call into
    buildpolaris_bff's MCP surface â€” reusing the exact assertion token it
    was handed, not re-minting one (the sidecar has no signing authority
    over Scope Assertions; only the BFF does)."""
    return {
        "X-Service-Key": ai_service_key,
        "X-Scope-Assertion": raw_assertion_token,
        "X-On-Behalf-Of-User": assertion.user,
        "X-On-Behalf-Of-Role": assertion.role,
    }
