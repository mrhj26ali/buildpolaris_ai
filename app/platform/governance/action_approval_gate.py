"""ActionApprovalGateClient -- deliberately thin (ARCH Flowchart 4: "the
port is intentionally narrow ... it only proposes, never resolves; the
approval record lives in BFF's MariaDB"). This client has exactly one
capability: hand a verified ProposedAction to buildpolaris_bff and get
back a reference to the Pending approval row it created. It has no
method that could ever mark something approved -- that would require
this sidecar to be trusted with a capability it structurally must never
have (FR-8.6).

Calls buildpolaris_bff.ai_copilot.api.propose_agent_action -- the ONE
entrypoint any task-specific agent uses to request a gated write. That
function's signature is:

    propose_agent_action(agent_type, target_doctype, payload,
                          scope_assertion, model_version=None,
                          confidence=None, tool_trace_id=None,
                          idempotency_key=None)

so every one of those (scope_assertion included) is sent as an explicit
JSON body field, not a header -- Frappe binds a whitelisted method's
keyword arguments from the request body/query string.
"""
from __future__ import annotations

from app.exceptions import ApprovalProposalError
from app.observability.logging import get_logger
from app.platform.bff.bff_client import BFFClient, BFFCallError
from app.platform.governance.payload_verifier import verify_proposed_action
from app.platform.governance.proposal_schema import ProposedAction

logger = get_logger(__name__)


class ActionApprovalGateClient:
    def __init__(self, raw_scope_assertion_token: str) -> None:
        self._raw_assertion = raw_scope_assertion_token
        self._client = BFFClient()

    async def propose(self, action: ProposedAction) -> str:
        """Returns the BFF's Agent Action Approval record name. Raises
        ApprovalProposalError on any failure -- callers must treat a
        failed proposal as a failed agent run, never as a silent
        success."""
        verify_proposed_action(action)

        body = {
            "agent_type": action.agent_type,
            "target_doctype": action.target_doctype,
            # Frappe whitelisted methods accept dict-typed kwargs as a
            # JSON body value directly (not double-encoded) when the
            # request Content-Type is application/json.
            "payload": action.payload,
            "scope_assertion": self._raw_assertion,
            "model_version": action.model_version,
            "confidence": action.confidence,
            "tool_trace_id": action.tool_trace_id,
            "idempotency_key": action.idempotency_key,
        }

        try:
            data = await self._client.post(
                self._client.settings.propose_agent_action_path, json=body,
            )
        except BFFCallError as exc:
            logger.error("approval_proposal_failed", agent_type=action.agent_type, error=str(exc))
            raise ApprovalProposalError(str(exc)) from exc

        # proposal_service.propose() returns action.as_dict() -- the
        # Agent Action Approval doc's own primary key field is `name`,
        # there is no separate `approval_name` field.
        approval_ref = data.get("name") if isinstance(data, dict) else None
        if not approval_ref:
            raise ApprovalProposalError("buildpolaris_bff did not return an approval reference")

        logger.info("approval_proposed", agent_type=action.agent_type, approval_ref=approval_ref)
        return approval_ref
