"""Circuit breaker â€” falls back from a rate-limited/exhausted primary
provider to a secondary provider or a locally-hosted Ollama model,
without any agent code knowing a fallback occurred (ARCH Â§3.3 point 2).

Per-provider breaker state: CLOSED (healthy) -> OPEN (failing, calls
short-circuit) -> HALF_OPEN (probe) -> CLOSED. Standard breaker shape,
kept intentionally simple (thresholds from ResilienceSettings) rather
than pulling in a breaker library for three states and one counter.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, TypeVar

from app.config import get_settings
from app.exceptions import ModelProviderUnavailableError
from app.observability.logging import get_logger
from app.observability.metrics import CIRCUIT_BREAKER_TRIPS_TOTAL, counters

logger = get_logger(__name__)
T = TypeVar("T")


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _ProviderBreaker:
    name: str
    failure_count: int = 0
    state: BreakerState = BreakerState.CLOSED
    opened_at: float | None = None

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = BreakerState.CLOSED
        self.opened_at = None

    def record_failure(self, threshold: int) -> None:
        self.failure_count += 1
        if self.failure_count >= threshold and self.state != BreakerState.OPEN:
            self.state = BreakerState.OPEN
            self.opened_at = time.monotonic()
            counters.increment(CIRCUIT_BREAKER_TRIPS_TOTAL)
            logger.warning("circuit_breaker_opened", provider=self.name)

    def allows_call(self, recovery_seconds: float) -> bool:
        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.OPEN:
            if self.opened_at and (time.monotonic() - self.opened_at) >= recovery_seconds:
                self.state = BreakerState.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN: allow exactly one probe through


class CircuitBreakerRegistry:
    """One breaker per provider name; the model_provider factory routes
    every call through `call_with_breaker`."""

    def __init__(self) -> None:
        self._breakers: dict[str, _ProviderBreaker] = {}

    def _get(self, provider_name: str) -> _ProviderBreaker:
        return self._breakers.setdefault(provider_name, _ProviderBreaker(name=provider_name))

    async def call_with_breaker(self, provider_name: str, fn: Callable[[], T]) -> T:
        settings = get_settings().resilience
        breaker = self._get(provider_name)

        if not breaker.allows_call(settings.breaker_recovery_seconds):
            raise ModelProviderUnavailableError(f"provider '{provider_name}' circuit open")

        try:
            result = await fn()
        except Exception:
            breaker.record_failure(settings.breaker_failure_threshold)
            raise
        else:
            breaker.record_success()
            return result

    def all_providers_open(self) -> bool:
        if not self._breakers:
            return False
        return all(b.state == BreakerState.OPEN for b in self._breakers.values())

    def snapshot(self) -> dict[str, str]:
        return {name: b.state.value for name, b in self._breakers.items()}


_registry = CircuitBreakerRegistry()


def get_circuit_breaker() -> CircuitBreakerRegistry:
    return _registry
