"""ProviderGuard: the single place that applies breaker, quota and retry to vendor calls.

Adapters stay dumb. ``wrap_market`` and ``wrap_news`` return objects with the same Protocol
interface as the adapter they wrap, with every method routed through ``guard.call``, so services
never know the guard exists. Every attempt (including retries) consumes quota, because the vendor
counts retries against us too.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from functools import partial
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.clock import utc_now
from app.config import ProviderLimits
from app.logging_setup import get_logger
from app.providers.base import MarketDataProvider, NewsProvider
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
from app.providers.models import (
    Bar,
    CorporateEvent,
    Interval,
    NewsItem,
    NewsQuery,
    Quote,
    SymbolMatch,
)
from app.providers.quota import QuotaLedgerPort, current_priority, daily_cap

log = get_logger(__name__)

MAX_HONOURED_RETRY_AFTER = 30.0  # longer vendor waits are not worth blocking a request on
MAX_QUOTA_WAIT = 65.0  # seconds; one minute window plus a margin
MAX_QUOTA_WAITS = 5


Level = Literal["ok", "warning", "blocked"]


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
    level: Level
    message: str


class ProviderGuard:
    def __init__(
        self,
        ledger: QuotaLedgerPort,
        limits: Mapping[str, ProviderLimits],
        warning_ratio: float,
        *,
        max_attempts: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], datetime] = utc_now,
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

    def wrap_market(self, adapter: MarketDataProvider) -> MarketDataProvider:
        """``adapter`` with every method run under the guard. Raises ValueError if unconfigured."""
        self._require_limits(adapter.name)
        return _GuardedMarket(self, adapter)

    def wrap_news(self, adapter: NewsProvider) -> NewsProvider:
        """``adapter`` with ``fetch`` run under the guard. Raises ValueError if unconfigured.

        News is only ever fetched by background ingestion, so a per-minute throttle pauses and
        retries instead of raising; a daily quota error always propagates.
        """
        self._require_limits(adapter.name)
        return _GuardedNews(self, adapter)

    def _require_limits(self, provider: str) -> None:
        # Checked at wrap time so a misnamed adapter fails at startup, not on its first call.
        if provider not in self._limits:
            raise ValueError(f"no quota limits configured for provider {provider!r}")

    async def call[T](self, provider: str, operation: Callable[[], Awaitable[T]]) -> T:
        """Run ``operation`` under breaker, quota and retry. Raises only ``ProviderError``s."""
        breaker = self.breaker(provider)
        if not breaker.allow():
            raise CircuitOpenError(provider, "circuit breaker is open; call skipped")
        limits = self._limits[provider]
        attempt = 0
        while True:
            attempt += 1
            decision = await self._ledger.try_consume(
                provider, limits, self._clock(), current_priority()
            )
            if not decision.allowed:
                # Our own throttle is not a vendor failure, so it must not trip the breaker,
                # but a half_open trial slot must be handed back.
                breaker.release_trial()
                raise QuotaExhaustedError(
                    provider,
                    f"{decision.window_blocked} quota exhausted; call not made",
                    window=decision.window_blocked,
                    retry_at=decision.retry_at,
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

    async def call_patiently[T](self, provider: str, operation: Callable[[], Awaitable[T]]) -> T:
        """Like ``call``, but waits out a per-minute quota block instead of failing.

        For background work only. At most ``MAX_QUOTA_WAITS`` pauses (so ``MAX_QUOTA_WAITS + 1``
        attempts); a daily quota error always propagates since waiting cannot help.
        """
        waits = 0
        while True:
            try:
                return await self.call(provider, operation)
            except QuotaExhaustedError as exc:
                waits += 1
                if exc.window != "minute" or waits > MAX_QUOTA_WAITS:
                    raise
                wait = MAX_QUOTA_WAIT
                if exc.retry_at is not None:
                    until_open = (exc.retry_at - self._clock()).total_seconds()
                    wait = min(MAX_QUOTA_WAIT, max(0.0, until_open))
                log.info("news_backfill_paused", provider=provider, wait_seconds=round(wait, 1))
                await self._sleep(wait)

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
        return list(
            await asyncio.gather(
                *(
                    self._status(provider, limits, configured.get(provider, False), now)
                    for provider, limits in self._limits.items()
                )
            )
        )

    async def _status(
        self, provider: str, limits: ProviderLimits, configured: bool, now: datetime
    ) -> ProviderStatus:
        snap, err = await asyncio.gather(
            self._ledger.snapshot(provider, limits, now), self._ledger.last_error(provider)
        )
        state = self.breaker(provider).state
        used, limit = snap.used_today, snap.daily_limit
        ratio = used / limit if limit else 1.0
        level: Level
        interactive_cap = daily_cap(limit, "interactive")
        # One ladder, worst first: the level and the sentence shown for it cannot disagree.
        if state == "open":
            level = "blocked"
            message = "Circuit breaker open after repeated failures; calls paused briefly."
        elif used >= limit:
            level = "blocked"
            message = f"Daily limit reached: {used} of {limit} calls used; blocked until 00:00 UTC."
        elif used >= interactive_cap:
            level = "warning"
            message = (
                f"Reserve in use: {used} of {limit} calls used today. The last "
                f"{limit - interactive_cap} calls are held back for scheduled refreshes, so "
                "user requests are paused until 00:00 UTC."
            )
        elif state == "half_open":
            level = "warning"
            message = "Recovering: trial call pending after repeated failures."
        elif ratio >= self._warning_ratio:
            level = "warning"
            message = (
                f"Approaching free-tier limit: {used} of {limit} calls used today; "
                f"resets 00:00 UTC. The last {limit - interactive_cap} calls are reserved for "
                "scheduled refreshes."
            )
        else:
            level = "ok"
            message = f"{used} of {limit} calls used today."
        return ProviderStatus(
            provider=provider,
            configured=configured,
            used_today=used,
            daily_limit=limit,
            used_ratio=ratio,
            resets_at=snap.resets_at,
            breaker_state=state,
            last_error=err[0] if err else None,
            last_error_at=err[1] if err else None,
            level=level,
            message=message,
        )


class _GuardedMarket:
    """A ``MarketDataProvider`` whose every call runs under the guard."""

    def __init__(self, guard: ProviderGuard, adapter: MarketDataProvider) -> None:
        self.name = adapter.name
        self._guard = guard
        self._adapter = adapter

    async def search(self, query: str) -> list[SymbolMatch]:
        return await self._guard.call(self.name, partial(self._adapter.search, query))

    async def quote(self, symbol: str) -> Quote:
        return await self._guard.call(self.name, partial(self._adapter.quote, symbol))

    async def bars(
        self, symbol: str, interval: Interval, start: datetime, end: datetime
    ) -> list[Bar]:
        return await self._guard.call(
            self.name, partial(self._adapter.bars, symbol, interval, start, end)
        )

    async def events(self, symbol: str, start: datetime, end: datetime) -> list[CorporateEvent]:
        return await self._guard.call(self.name, partial(self._adapter.events, symbol, start, end))


class _GuardedNews:
    """A ``NewsProvider`` whose ``fetch`` runs under the guard (and waits out minute quotas)."""

    def __init__(self, guard: ProviderGuard, adapter: NewsProvider) -> None:
        self.name = adapter.name
        self.exchanges = adapter.exchanges
        self._guard = guard
        self._adapter = adapter

    async def fetch(self, query: NewsQuery) -> list[NewsItem]:
        return await self._guard.call_patiently(self.name, partial(self._adapter.fetch, query))
