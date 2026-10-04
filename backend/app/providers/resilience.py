"""ProviderGuard: the single place that applies breaker, quota and retry to vendor calls.

Adapters stay dumb; the service layer wraps each adapter call in ``guard.call``. Every attempt
(including retries) consumes quota, because the vendor counts retries against us too.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.config import ProviderLimits
from app.logging_setup import get_logger
from app.providers.breaker import BreakerState, CircuitBreaker
from app.providers.errors import (
    CircuitOpenError,
    ProviderDataError,
    ProviderError,
    QuotaExhaustedError,
    RateLimitedError,
    SymbolNotFoundError,
    TransientProviderError,
)
from app.providers.quota import QuotaLedgerLike

log = get_logger(__name__)

MAX_HONOURED_RETRY_AFTER = 30.0  # longer vendor waits are not worth blocking a request on


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProviderStatus(BaseModel):
    """What the admin page shows for one provider."""

    model_config = ConfigDict(frozen=True)

    provider: str
    configured: bool
    used_today: int
    daily_limit: int
    used_ratio: float
    resets_at: AwareDatetime
    breaker_state: BreakerState
    last_error: str | None
    last_error_at: AwareDatetime | None
    level: Literal["ok", "warning", "blocked"]
    message: str


class ProviderGuard:
    def __init__(
        self,
        ledger: QuotaLedgerLike,
        limits: Mapping[str, ProviderLimits],
        warning_ratio: float,
        *,
        max_attempts: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._ledger = ledger
        self._limits = limits
        self._warning_ratio = warning_ratio
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._sleep = sleep
        self._clock = clock
        self._breakers: dict[str, CircuitBreaker] = {}

    def breaker(self, provider: str) -> CircuitBreaker:
        if provider not in self._breakers:
            self._breakers[provider] = CircuitBreaker(clock=self._clock)
        return self._breakers[provider]

    async def call[T](self, provider: str, operation: Callable[[], Awaitable[T]]) -> T:
        """Run ``operation`` under breaker, quota and retry. Raises only ``ProviderError``s."""
        breaker = self.breaker(provider)
        if not breaker.allow():
            raise CircuitOpenError(provider, "circuit breaker is open; call skipped")
        limits = self._limits[provider]
        attempt = 0
        while True:
            attempt += 1
            decision = await self._ledger.try_consume(provider, limits, self._clock())
            if not decision.allowed:
                # Our own throttle is not a vendor failure, so it must not trip the breaker,
                # but a half_open trial slot must be handed back.
                breaker.release_trial()
                raise QuotaExhaustedError(
                    provider, f"{decision.window_blocked} quota exhausted; call not made"
                )
            try:
                result = await operation()
            except SymbolNotFoundError:
                breaker.record_success()  # the vendor answered fine; the symbol is just unknown
                raise
            except RateLimitedError as exc:
                log.error(  # noqa: TRY400 - not an active exception handler log
                    "provider_rate_limited", provider=provider, retry_after=exc.retry_after
                )
                wait = exc.retry_after
                if wait is not None and wait > MAX_HONOURED_RETRY_AFTER:
                    await self._fail(provider, exc)
                    raise
                if attempt >= self._max_attempts:
                    await self._fail(provider, exc)
                    raise
                await self._sleep(wait if wait is not None else self._backoff(attempt))
            except TransientProviderError as exc:
                if attempt >= self._max_attempts:
                    await self._fail(provider, exc)
                    raise
                await self._sleep(self._backoff(attempt))
            except ProviderError as exc:
                await self._fail(provider, exc)
                raise
            else:
                breaker.record_success()
                return result

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter, capped."""
        ceiling = min(self._max_delay, self._base_delay * 2 ** (attempt - 1))
        return random.uniform(0, ceiling)  # noqa: S311 - jitter, not security

    async def _fail(self, provider: str, exc: ProviderError) -> None:
        self.breaker(provider).record_failure()
        await self._ledger.record_error(provider, str(exc), self._clock())
        if isinstance(exc, ProviderDataError):
            log.warning("provider_data_error", provider=provider, error=str(exc))

    async def statuses(self, configured: Mapping[str, bool]) -> list[ProviderStatus]:
        now = self._clock()
        out: list[ProviderStatus] = []
        for provider, limits in self._limits.items():
            snap = await self._ledger.snapshot(provider, limits, now)
            err = await self._ledger.last_error(provider)
            state = self.breaker(provider).state
            ratio = snap.used_today / snap.daily_limit if snap.daily_limit else 1.0
            if snap.used_today >= snap.daily_limit or state == "open":
                level: Literal["ok", "warning", "blocked"] = "blocked"
            elif ratio >= self._warning_ratio or state == "half_open":
                level = "warning"
            else:
                level = "ok"
            out.append(
                ProviderStatus(
                    provider=provider,
                    configured=configured.get(provider, False),
                    used_today=snap.used_today,
                    daily_limit=snap.daily_limit,
                    used_ratio=ratio,
                    resets_at=snap.resets_at,
                    breaker_state=state,
                    last_error=err[0] if err else None,
                    last_error_at=err[1] if err else None,
                    level=level,
                    message=_message(level, state, snap.used_today, snap.daily_limit),
                )
            )
        return out


def _message(level: str, state: BreakerState, used: int, limit: int) -> str:
    if state == "open":
        return "Circuit breaker open after repeated failures; calls paused briefly."
    if level == "blocked":
        return f"Daily limit reached: {used} of {limit} calls used; blocked until 00:00 UTC."
    if state == "half_open":
        return "Recovering: trial call pending after repeated failures."
    if level == "warning":
        return f"Approaching free-tier limit: {used} of {limit} calls used today; resets 00:00 UTC."
    return f"{used} of {limit} calls used today."
