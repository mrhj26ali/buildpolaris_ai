"""Defensive shape checks on a ProposedAction before it's handed to the
BFF (FR-8.6: "no agent implements its own approval flow" implies every
proposal passes through the same minimal sanity gate here first, so a
malformed agent output fails loudly in this sidecar rather than as an
opaque 400 from the BFF).
"""
from __future__ import annotations

from app.platform.governance.proposal_schema import ProposedAction

# Target DocTypes an agent is permitted to propose a write against, per
# REQ v2.1's agent catalog (RFI drafting -> RFI, submittal review ->
# Submittal Package/Submittal Item, daily-log extraction -> Daily Log,
# contract-clause extraction -> Commitment). Kept centralized rather than
# per-agent so adding a target requires one reviewed change here, not a
# silent capability added inside a handler.
ALLOWED_TARGETS = {
    "rfi_drafting": {"RFI"},
    "submittal_review": {"Submittal Package", "Submittal Item"},
    "daily_log_extraction": {"Daily Log"},
    "contract_clause_extraction": {"Commitment"},
}


class PayloadVerificationError(Exception):
    pass


def verify_proposed_action(action: ProposedAction) -> None:
    allowed = ALLOWED_TARGETS.get(action.agent_type)
    if allowed is None:
        raise PayloadVerificationError(f"unknown agent_type '{action.agent_type}'")
    if action.target_doctype not in allowed:
        raise PayloadVerificationError(
            f"agent '{action.agent_type}' is not allowed to propose a write "
            f"against '{action.target_doctype}'"
        )
    if not action.payload:
        raise PayloadVerificationError("proposed payload is empty")
    if not action.company:
        raise PayloadVerificationError("proposed action missing company scope")
