"""Approval-gate reliability metric â€” of a golden set of proposed-action
scenarios, how often the agent produced a well-formed ProposedAction that
passed payload_verifier.py's shape checks on the first attempt. This is
NOT about whether a human would have approved the content â€” it measures
mechanical reliability of the gate itself.
"""
from __future__ import annotations

from app.platform.governance.payload_verifier import PayloadVerificationError, verify_proposed_action
from app.platform.governance.proposal_schema import ProposedAction


def score_approval_gate_accuracy(proposed_actions: list[ProposedAction]) -> dict:
    total = len(proposed_actions)
    passed = 0
    failures: list[str] = []

    for action in proposed_actions:
        try:
            verify_proposed_action(action)
            passed += 1
        except PayloadVerificationError as exc:
            failures.append(str(exc))

    accuracy = passed / total if total else None
    return {
        "metric": "approval_gate_accuracy", "total_cases": total, "passed": passed,
        "accuracy": accuracy, "failures": failures,
    }
