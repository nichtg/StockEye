from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from structlog.testing import capture_logs

from app.config import ProviderLimits
from app.db import Database
from app.providers.errors import (
    CircuitOpenError,
    ProviderDataError,
    ProviderError,
    QuotaExhaustedError,
    RateLimitedError,
    SymbolNotFoundError,
    TransientProviderError,
)
from app.providers.resilience import ProviderGuard
from app.repositories.quotas import QuotaDecision, QuotaLedger, QuotaSnapshot, install_indexes

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
LIMITS = {"p": ProviderLimits(per_minute=100, per_day=100)}


class FakeLedger:
    """In-memory stand-in so guard logic is tested without Mongo."""

    def __init__(self, allow: int = 10_000, used: int = 0) -> None:
        self.consumed = 0
        self._allow = allow
        self._used = used
        self.errors: list[str] = []

    async def try_consume(
        self, provider: str, limits: ProviderLimits, now: datetime
    ) -> QuotaDecision:
        if self.consumed >= self._allow:
            return QuotaDecision(False, "day", self.consumed, limits.per_day, None)
        self.consumed += 1
        return QuotaDecision(True, None, self.consumed, limits.per_day, None)

    async def snapshot(self, provider: str, limits: ProviderLimits, now: datetime) -> QuotaSnapshot:
        return QuotaSnapshot(self._used, limits.per_day, datetime(2026, 3, 11, tzinfo=UTC))

    async def record_error(self, provider: str, message: str, now: datetime) -> None:
        self.errors.append(message)

    async def last_error(self, provider: str) -> tuple[str, datetime] | None:
        return (self.errors[-1], NOW) if self.errors else None


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@dataclass
class Harness:
    guard: ProviderGuard
    ledger: FakeLedger
    sleeps: list[float]
    clock: Clock


def _harness(
    ledger: FakeLedger | None = None, limits: dict[str, ProviderLimits] = LIMITS
) -> Harness:
    sleeps: list[float] = []
    clock = Clock()
    fake = ledger or FakeLedger()

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    guard = ProviderGuard(fake, limits, 0.8, sleep=fake_sleep, clock=clock)
    return Harness(guard, fake, sleeps, clock)


def _flaky(*outcomes: object) -> Callable[[], Awaitable[str]]:
    queue = list(outcomes)

    async def operation() -> str:
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return str(outcome)

    return operation


async def test_call_success_returns_result_and_consumes_one_call() -> None:
    h = _harness()

    assert await h.guard.call("p", _flaky("ok")) == "ok"
    assert h.ledger.consumed == 1


async def test_call_503_then_success_retries_and_consumes_two_quota() -> None:
    h = _harness()

    result = await h.guard.call("p", _flaky(TransientProviderError("p", "503"), "ok"))

    assert result == "ok"
    assert h.ledger.consumed == 2
    assert len(h.sleeps) == 1
    assert 0 <= h.sleeps[0] <= 0.5


async def test_call_timeouts_until_attempts_exhausted_raises_and_records_error() -> None:
    h = _harness()
    err = TransientProviderError("p", "request timed out")

    with pytest.raises(TransientProviderError):
        await h.guard.call("p", _flaky(err, err, err))

    assert h.ledger.consumed == 3
    assert h.ledger.errors == [str(err)]


async def test_call_backoff_is_capped_at_max_delay() -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    guard = ProviderGuard(
        FakeLedger(), LIMITS, 0.8, max_attempts=6, base_delay=4.0, max_delay=8.0, sleep=fake_sleep
    )
    err = TransientProviderError("p", "boom")

    with pytest.raises(TransientProviderError):
        await guard.call("p", _flaky(*[err] * 6))

    assert len(sleeps) == 5
    assert all(0 <= s <= 8.0 for s in sleeps)


async def test_call_429_with_short_retry_after_sleeps_exactly_that_long_and_logs_error() -> None:
    h = _harness()

    with capture_logs() as logs:
        result = await h.guard.call("p", _flaky(RateLimitedError("p", retry_after=7), "ok"))

    assert result == "ok"
    assert h.sleeps == [7]
    limited = [e for e in logs if e["event"] == "provider_rate_limited"]
    assert len(limited) == 1
    assert limited[0]["provider"] == "p"
    assert limited[0]["log_level"] == "error"


async def test_call_429_with_long_retry_after_gives_up_immediately() -> None:
    h = _harness()

    with pytest.raises(RateLimitedError):
        await h.guard.call("p", _flaky(RateLimitedError("p", retry_after=120), "never"))

    assert h.ledger.consumed == 1
    assert h.sleeps == []


async def test_call_symbol_not_found_propagates_without_retry_or_breaker_failure() -> None:
    h = _harness()
    missing = SymbolNotFoundError("p", "nope")

    for _ in range(10):
        with pytest.raises(SymbolNotFoundError):
            await h.guard.call("p", _flaky(missing))

    assert h.guard.breaker("p").state == "closed"
    assert h.ledger.errors == []
    assert h.ledger.consumed == 10  # one attempt per call, no retries


async def test_call_data_error_is_not_retried_but_counts_as_breaker_failure() -> None:
    h = _harness()

    for _ in range(5):
        with pytest.raises(ProviderDataError):
            await h.guard.call("p", _flaky(ProviderDataError("p", "bad")))

    assert h.ledger.consumed == 5
    assert h.guard.breaker("p").state == "open"


async def test_call_breaker_opens_after_five_failures_then_half_opens_after_cooldown() -> None:
    h = _harness()
    boom = ProviderError("p", "creds")
    for _ in range(5):
        with pytest.raises(ProviderError):
            await h.guard.call("p", _flaky(boom))

    with pytest.raises(CircuitOpenError):
        await h.guard.call("p", _flaky("unused"))
    consumed_while_open = h.ledger.consumed
    h.clock.now += timedelta(minutes=2)

    assert await h.guard.call("p", _flaky("recovered")) == "recovered"
    assert consumed_while_open == 5  # the refused call cost no quota
    assert h.guard.breaker("p").state == "closed"


async def test_call_blocked_by_quota_raises_without_calling_operation() -> None:
    h = _harness(FakeLedger(allow=0))
    called = False

    async def operation() -> str:
        nonlocal called
        called = True
        return "x"

    with pytest.raises(QuotaExhaustedError):
        await h.guard.call("p", operation)

    assert not called
    assert h.guard.breaker("p").state == "closed"


async def test_call_retry_blocked_mid_way_by_quota_raises_quota_error() -> None:
    h = _harness(FakeLedger(allow=1))

    with pytest.raises(QuotaExhaustedError):
        await h.guard.call("p", _flaky(TransientProviderError("p", "503"), "ok"))

    assert h.ledger.consumed == 1


@pytest.mark.parametrize(
    ("used", "level"),
    [(0, "ok"), (79, "ok"), (80, "warning"), (99, "warning"), (100, "blocked")],
)
async def test_statuses_level_follows_usage_ratio(used: int, level: str) -> None:
    h = _harness(FakeLedger(used=used))

    [status] = await h.guard.statuses({"p": True})

    assert status.level == level
    assert status.used_today == used
    assert status.used_ratio == used / 100


async def test_statuses_warning_message_is_human_readable() -> None:
    h = _harness(FakeLedger(used=21), {"p": ProviderLimits(per_minute=5, per_day=25)})

    [status] = await h.guard.statuses({"p": True})

    assert status.message == (
        "Approaching free-tier limit: 21 of 25 calls used today; resets 00:00 UTC."
    )


async def test_statuses_open_breaker_is_blocked_and_half_open_is_warning() -> None:
    h = _harness()
    for _ in range(5):
        with pytest.raises(ProviderError):
            await h.guard.call("p", _flaky(ProviderError("p", "creds")))

    [open_status] = await h.guard.statuses({"p": True})
    h.clock.now += timedelta(minutes=2)
    [half_status] = await h.guard.statuses({"p": True})

    assert (open_status.level, open_status.breaker_state) == ("blocked", "open")
    assert (half_status.level, half_status.breaker_state) == ("warning", "half_open")
    assert open_status.last_error is not None
    assert open_status.last_error_at == NOW


async def test_statuses_unconfigured_provider_is_reported_as_such() -> None:
    h = _harness()

    [status] = await h.guard.statuses({})

    assert status.configured is False


@pytest.mark.integration
async def test_call_with_real_ledger_503_then_success_consumes_two_in_mongo(db: Database) -> None:
    await install_indexes(db)
    ledger = QuotaLedger(db)

    async def fake_sleep(_: float) -> None:
        return None

    guard = ProviderGuard(ledger, LIMITS, 0.8, sleep=fake_sleep, clock=lambda: NOW)

    await guard.call("p", _flaky(TransientProviderError("p", "503"), "ok"))

    assert (await ledger.snapshot("p", LIMITS["p"], NOW)).used_today == 2
