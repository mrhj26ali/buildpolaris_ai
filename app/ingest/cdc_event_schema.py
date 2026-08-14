"""Internal representation of a change-data-capture event driving the
entity mirror (ERD Â§4.3: nodes/edges "mirror MariaDB, never hand-
curated"). Distinct from gateway/schemas/graph_sync_event.py, which is
the wire shape â€” this is what projector.py actually operates on after
gateway/routers/graph_sync.py has parsed and validated the inbound
request.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(slots=True)
class CDCEvent:
    company: str
    event_type: Literal["after_insert", "on_update", "on_trash"]
    source_doctype: str
    source_name: str
    project: str | None
    properties: dict[str, Any]
    event_seq: int
