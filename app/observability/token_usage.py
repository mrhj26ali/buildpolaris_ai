"""Per-tenant LLM/embedding spend tracking (NFR-AIGOV.1).

Feeds the soft-ceiling-before-hard-denial alerting the requirement asks
for: "an uncapped agent loop or a runaway retrieval query must not be
discoverable only via the monthly bill." In-memory + Postgres-backed
counter in v1; swappable for a dedicated billing-metrics store later
without touching callers, since everything routes through record_usage().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from app.config import get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _TenantUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    request_count: int = 0


class TokenUsageTracker:
    """Process-local accumulator. In a multi-worker deployment this is
    naturally sharded per worker; NFR-AIGOV.1 only requires *observability*
    and a *soft* ceiling with alerting, not perfectly synchronized global
    counting, so this is sufficient without introducing a shared-state
    dependency purely for a soft alert threshold."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._usage: dict[str, _TenantUsage] = {}

    def record_usage(
        self, company: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        settings = get_settings().governance
        with self._lock:
            u = self._usage.setdefault(company, _TenantUsage())
            u.prompt_tokens += prompt_tokens
            u.completion_tokens += completion_tokens
            u.request_count += 1
            total = u.prompt_tokens + u.completion_tokens

        if total >= settings.token_hard_ceiling_per_tenant:
            logger.error(
                "tenant_token_hard_ceiling_reached", company=company, total_tokens=total
            )
        elif total >= settings.token_soft_ceiling_per_tenant:
            logger.warning(
                "tenant_token_soft_ceiling_reached", company=company, total_tokens=total
            )

    def snapshot(self, company: str) -> dict:
        with self._lock:
            u = self._usage.get(company, _TenantUsage())
            return {
                "company": company,
                "prompt_tokens": u.prompt_tokens,
                "completion_tokens": u.completion_tokens,
                "total_tokens": u.prompt_tokens + u.completion_tokens,
                "request_count": u.request_count,
            }

    def all_snapshots(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "company": company,
                    "prompt_tokens": u.prompt_tokens,
                    "completion_tokens": u.completion_tokens,
                    "total_tokens": u.prompt_tokens + u.completion_tokens,
                    "request_count": u.request_count,
                }
                for company, u in self._usage.items()
            ]


_tracker = TokenUsageTracker()


def get_token_usage_tracker() -> TokenUsageTracker:
    return _tracker
