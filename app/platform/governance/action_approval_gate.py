"""ActionApprovalGateClient â€” deliberately thin (ARCH Â§3.3 point 3: "the
port is intentionally narrow ... it only proposes, never resolves; the
approval record lives in BFF's MariaDB"). This client has exactly one
capability: hand a verified ProposedAction to the BFF and get back a
reference to the Pending approval row it created. It has no method that
could ever mark something approved â€” that would require this sidecar to
be trusted with a capability it structurally must never have (FR-8.6).
"""
from __future__ import annotations

import httpx

from app.config import get_settings
from app.exceptions import ApprovalProposalError
from app.observability.logging import get_logger
from app.platform.governance.payload_verifier import verify_proposed_action
from app.platform.governance.proposal_schema import ProposedAction

logger = get_logger(__name__)


class ActionApprovalGateClient:
    def __init__(self, raw_scope_assertion_token: str) -> None:
        self._settings = get_settings().bff
        self._raw_assertion = raw_scope_assertion_token

    async def propose(self, action: ProposedAction) -> str:
        """Returns the BFF's Agent Action Approval record name. Raises
        ApprovalProposalError on any failure â€” callers must treat a failed
        proposal as a failed agent run, never as a silent success."""
        verify_proposed_action(action)

        headers = {
            "X-Service-Key": self._settings.service_key.get_secret_value(),
            "X-Scope-Assertion": self._raw_assertion,
            "Idempotency-Key": action.idempotency_key,
        }

        url = f"{self._settings.base_url}/api/method/buildpolaris_bff.ai_copilot.approval_gate.propose_action"
        async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
            try:
                response = await client.post(url, json=action.model_dump(), headers=headers)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.error("approval_proposal_failed", agent_type=action.agent_type, error=str(exc))
                raise ApprovalProposalError(str(exc)) from exc

        data = response.json()
        approval_ref = data.get("message", {}).get("approval_name") or data.get("approval_name")
        if not approval_ref:
            raise ApprovalProposalError("BFF did not return an approval reference")

        logger.info("approval_proposed", agent_type=action.agent_type, approval_ref=approval_ref)
        return approval_ref
