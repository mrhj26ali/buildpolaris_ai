"""Shared helpers every agents/<name>/handler.py uses so the boilerplate
of assembling a ProposedAction (idempotency key, tool_trace_id, common
fields) lives in one place, not copy-pasted into four handlers.
"""
from __future__ import annotations

import hashlib
import uuid

from app.orchestrator.context import TurnContext
from app.platform.governance.proposal_schema import ProposedAction


def make_idempotency_key(context: TurnContext, agent_type: str) -> str:
    """Stable for a given (thread, agent_type, message) so a client retry
    of the same turn doesn't produce a second Pending approval row."""
    raw = f"{context.thread_id}:{agent_type}:{context.message}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def make_tool_trace_id() -> str:
    return uuid.uuid4().hex


def build_proposed_action(
    context: TurnContext, agent_type: str, target_doctype: str, payload: dict,
    model_version: str, confidence: float,
) -> ProposedAction:
    return ProposedAction(
        agent_type=agent_type,
        target_doctype=target_doctype,
        company=context.company,
        project=context.project,
        payload=payload,
        model_version=model_version,
        confidence=confidence,
        tool_trace_id=make_tool_trace_id(),
        idempotency_key=make_idempotency_key(context, agent_type),
        requested_by_user=context.user,
    )
