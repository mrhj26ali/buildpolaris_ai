"""Risk tier classification for agent actions."""
from __future__ import annotations

from typing import Literal

RiskTier = Literal["read", "write_gated", "write_autonomous_never"]


def is_approval_required(risk_tier: RiskTier) -> bool:
    """Return True if the action requires a human approval gate."""
    return risk_tier in {"write_gated", "write_autonomous_never"}


def is_read_only(risk_tier: RiskTier) -> bool:
    return risk_tier == "read"


def is_never_autonomous(risk_tier: RiskTier) -> bool:
    return risk_tier == "write_autonomous_never"
