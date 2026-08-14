"""trace_id propagation (NFR-OBS.1).

The trace_id originates at the PWA/job that started the request, is
forwarded by buildpolaris_bff on every call into this sidecar (ARCH Â§4.2),
and is threaded through every downstream log line and outbound call here
via a contextvar rather than being passed explicitly through every
function signature.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def get_trace_id() -> str:
    """Return the current trace_id, minting one if none is set (should
    only happen for sidecar-internal work with no inbound BFF request,
    e.g. a scheduled reconciliation task)."""
    current = trace_id_var.get()
    if current is None:
        current = new_trace_id()
        trace_id_var.set(current)
    return current


def set_trace_id(trace_id: str) -> None:
    trace_id_var.set(trace_id)
