"""Shared exception types for the AI sidecar.

Kept centralized so gateway/routers/*.py can map every one of these to a
correct HTTP status without each router re-inventing error shapes
(NFR-MAINT.1/.2).
"""
from __future__ import annotations


class BuildPolarisAIError(Exception):
    """Base class for every error this service raises deliberately."""


class InvalidServiceCredentialError(BuildPolarisAIError):
    """Caller did not present a valid X-Service-Key (ARCH Â§4.2 Direction 1)."""


class InvalidScopeAssertionError(BuildPolarisAIError):
    """Scope Assertion missing, expired, malformed, or signature mismatch."""


class ScopeMismatchError(BuildPolarisAIError):
    """Company/Project in a request doesn't match the asserted scope.

    UC-8.4 E3 â€” a defensive check applied to the ingestion write path too,
    not just reads (NFR-SEC.8).
    """


class UnknownAgentTypeError(BuildPolarisAIError):
    """OrchestrationLayer was asked to dispatch an agent_type with no
    registered module (FR-8.5 â€” should be structurally impossible if the
    orchestrator and the manifest registry stay in sync, but the caller-
    facing surface must still fail loudly rather than silently no-op)."""


class CitationValidationExhaustedError(BuildPolarisAIError):
    """UC-8.1 E2 â€” citation validation failed even after the single
    stricter-prompt retry. Callers must convert this into a refusal, never
    an unvalidated answer."""


class NoExtractableTextError(BuildPolarisAIError):
    """UC-8.4 E1 â€” no text layer found (e.g. scanned/image-only PDF).
    Carries a machine-readable reason so BFF can set
    AI Document Index.status = Failed(reason) rather than Indexed(empty)."""

    def __init__(self, reason: str = "no_text_layer") -> None:
        self.reason = reason
        super().__init__(reason)


class ModelProviderUnavailableError(BuildPolarisAIError):
    """All configured providers (primary + fallback) are unavailable.
    NFR-SCALE.5 requires the caller (BFF) to fail closed on this, not the
    sidecar silently degrading into a stale or fabricated answer."""


class ApprovalProposalError(BuildPolarisAIError):
    """ActionApprovalGateClient could not register a proposed write with
    the BFF. The sidecar never marks a write approved itself â€” if the
    proposal call fails, the agent output must be surfaced as failed, not
    silently treated as approved or discarded."""
