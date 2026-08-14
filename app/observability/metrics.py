"""Lightweight in-process metrics counters exposed via
gateway/routers/metrics.py. Not a full Prometheus client dependency in v1
â€” this is the minimum viable surface NFR-OBS.3's status endpoint and
NFR-AIGOV.1's spend dashboard need; swapping in prometheus_client later
only touches this module.
"""
from __future__ import annotations

import threading
from collections import defaultdict


class _Counters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)


counters = _Counters()

# Well-known counter names, referenced across the codebase rather than
# re-typed as string literals at every call site.
COPILOT_REQUESTS_TOTAL = "copilot_requests_total"
CITATION_VALIDATION_FAILURES_TOTAL = "citation_validation_failures_total"
CITATION_VALIDATION_REFUSALS_TOTAL = "citation_validation_refusals_total"
INGESTION_SUCCEEDED_TOTAL = "ingestion_succeeded_total"
INGESTION_FAILED_TOTAL = "ingestion_failed_total"
AGENT_RUNS_TOTAL = "agent_runs_total"
APPROVAL_PROPOSALS_TOTAL = "approval_proposals_total"
CIRCUIT_BREAKER_TRIPS_TOTAL = "circuit_breaker_trips_total"
