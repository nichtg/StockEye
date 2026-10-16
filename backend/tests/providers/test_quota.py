import asyncio
from collections.abc import MutableMapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from structlog.testing import capture_logs

from app.config import ProviderLimits
from app.db import Database
from app.repositories.quotas import QuotaLedger, install_indexes

NOW = datetime(2026, 3, 10, 12, 30, 15, tzinfo=UTC)
pytestmark = pytest.mark.integration


@pytest.fixture
async def ledger(db: Database) -> QuotaLedger:
    await install_indexes(db)
    return QuotaLedger(db, warning_ratio=0.8)


def _events(logs: list[MutableMapping[str, Any]], event: str) -> list[MutableMapping[str, Any]]:
    return [entry for entry in logs if entry["event"] == event]


async def test_try_consume_concurrent_calls_never_exceed_the_limit(ledger: QuotaLedger) -> None:
    limits = ProviderLimits(per_minute=1000, per_day=20)

    decisions = await asyncio.gather(
        *(ledger.try_consume("p", limits, NOW, "scheduled") for _ in range(50))
    )

    assert sum(d.allowed for d in decisions) == 20
    assert (await ledger.snapshot("p", limits, NOW)).used_today == 20


async def test_try_consume_minute_limit_blocks_then_resets_next_minute(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=2, per_day=100)

    first = [await ledger.try_consume("p", limits, NOW, "interactive") for _ in range(3)]
    later = await ledger.try_consume("p", limits, NOW + timedelta(minutes=1), "interactive")

    assert [d.allowed for d in first] == [True, True, False]
    assert first[2].window_blocked == "minute"
    assert first[2].retry_at == datetime(2026, 3, 10, 12, 31, tzinfo=UTC)
    assert later.allowed


async def test_try_consume_day_block_rolls_back_the_minute_increment(
    ledger: QuotaLedger, db: Database
) -> None:
    limits = ProviderLimits(per_minute=10, per_day=2)
    for _ in range(2):
        await ledger.try_consume("p", limits, NOW, "scheduled")

    blocked = await ledger.try_consume("p", limits, NOW, "scheduled")

    minute_doc = await db["provider_quota"].find_one({"provider": "p", "window": "minute"})
    assert blocked.window_blocked == "day"
    assert blocked.retry_at == datetime(2026, 3, 11, tzinfo=UTC)
    assert minute_doc is not None
    assert minute_doc["used"] == 2  # not 3: the blocked call was refunded


async def test_try_consume_logs_warning_exactly_once_at_eighty_percent(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=100, per_day=10)

    with capture_logs() as logs:
        for _ in range(10):
            await ledger.try_consume("alphavantage", limits, NOW, "scheduled")

    warnings = _events(logs, "provider_quota_warning")
    assert len(warnings) == 1
    assert warnings[0]["log_level"] == "warning"
    assert warnings[0]["used"] == 8
    assert warnings[0]["limit"] == 10
    assert warnings[0]["provider"] == "alphavantage"
    assert "8/10 calls today (80%)" in str(warnings[0]["message"])


async def test_try_consume_logs_error_exactly_once_when_day_limit_blocks(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=100, per_day=3)

    with capture_logs() as logs:
        for _ in range(6):
            await ledger.try_consume("p", limits, NOW, "scheduled")

    errors = _events(logs, "provider_quota_exhausted")
    assert len(errors) == 1
    assert errors[0]["log_level"] == "error"


async def test_try_consume_logs_one_throttle_warning_per_minute_window(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=1, per_day=100)

    with capture_logs() as logs:
        for _ in range(4):
            await ledger.try_consume("p", limits, NOW, "scheduled")
        await ledger.try_consume("p", limits, NOW + timedelta(minutes=1), "scheduled")
        await ledger.try_consume("p", limits, NOW + timedelta(minutes=1), "scheduled")

    assert len(_events(logs, "provider_rate_throttled")) == 2


async def test_try_consume_logs_reset_when_new_day_follows_a_warned_day(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=100, per_day=5)
    for _ in range(4):
        await ledger.try_consume("p", limits, NOW, "scheduled")

    with capture_logs() as logs:
        await ledger.try_consume("p", limits, NOW + timedelta(days=1), "scheduled")
        await ledger.try_consume("p", limits, NOW + timedelta(days=1), "scheduled")

    assert len(_events(logs, "provider_quota_reset")) == 1


async def test_try_consume_no_reset_log_when_previous_day_was_quiet(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=100, per_day=50)
    await ledger.try_consume("p", limits, NOW, "scheduled")

    with capture_logs() as logs:
        await ledger.try_consume("p", limits, NOW + timedelta(days=1), "scheduled")

    assert _events(logs, "provider_quota_reset") == []


async def test_snapshot_reports_usage_and_next_utc_midnight(ledger: QuotaLedger) -> None:
    limits = ProviderLimits(per_minute=100, per_day=50)
    await ledger.try_consume("p", limits, NOW, "scheduled")

    snap = await ledger.snapshot("p", limits, NOW)

    assert (snap.used_today, snap.daily_limit) == (1, 50)
    assert snap.resets_at == datetime(2026, 3, 11, tzinfo=UTC)


async def test_record_error_round_trips_latest_error(ledger: QuotaLedger) -> None:
    assert await ledger.last_error("p") is None

    await ledger.record_error("p", "first", NOW)
    await ledger.record_error("p", "second", NOW + timedelta(seconds=5))

    assert await ledger.last_error("p") == ("second", NOW + timedelta(seconds=5))


async def test_try_consume_interactive_stops_at_eighty_percent_scheduled_uses_the_rest(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=1000, per_day=10)

    interactive = [await ledger.try_consume("p", limits, NOW, "interactive") for _ in range(10)]
    scheduled = [await ledger.try_consume("p", limits, NOW, "scheduled") for _ in range(3)]

    assert sum(d.allowed for d in interactive) == 8
    assert [d.allowed for d in scheduled] == [True, True, False]
    assert (await ledger.snapshot("p", limits, NOW)).used_today == 10


async def test_try_consume_interactive_block_logs_reserved_warning_once(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=1000, per_day=10)

    with capture_logs() as logs:
        for _ in range(12):
            await ledger.try_consume("p", limits, NOW, "interactive")

    reserved = _events(logs, "provider_quota_reserved")
    assert len(reserved) == 1
    assert reserved[0]["log_level"] == "warning"
    assert _events(logs, "provider_quota_exhausted") == []  # the day is not actually used up


async def test_try_consume_interactive_calls_still_trigger_the_eighty_percent_warning(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=1000, per_day=25)

    with capture_logs() as logs:
        for _ in range(25):
            await ledger.try_consume("alphavantage", limits, NOW, "interactive")

    assert len(_events(logs, "provider_quota_warning")) == 1


async def test_try_consume_scheduled_calls_stop_at_their_minute_share(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=10, per_day=1000)

    scheduled = [await ledger.try_consume("p", limits, NOW, "scheduled") for _ in range(9)]
    interactive = [await ledger.try_consume("p", limits, NOW, "interactive") for _ in range(4)]

    assert [d.allowed for d in scheduled] == [True] * 7 + [False] * 2  # 70% of 10
    assert [d.allowed for d in interactive] == [True] * 3 + [False]  # the other 30% is theirs
    assert scheduled[-1].window_blocked == "minute"


async def test_throttle_log_names_priority_and_cap_and_keeps_one_flag_per_priority(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=10, per_day=100)

    with capture_logs() as logs:
        for _ in range(8):  # scheduled stops at 7 (70%); the 8th is blocked
            await ledger.try_consume("p", limits, NOW, "scheduled")
        for _ in range(3):  # interactive then spends the other 3
            await ledger.try_consume("p", limits, NOW, "interactive")
        await ledger.try_consume("p", limits, NOW, "interactive")  # a real interactive block
        await ledger.try_consume("p", limits, NOW, "interactive")  # same minute: not logged again

    throttled = _events(logs, "provider_rate_throttled")
    assert [(e["priority"], e["cap_applied"]) for e in throttled] == [
        ("scheduled", 7),
        ("interactive", 10),
    ]


async def _fresh_window_burst(ledger: QuotaLedger, limits: ProviderLimits, calls: int) -> int:
    """Allowed count over 10 fresh minute windows, each hit by ``calls`` concurrent callers."""
    allowed = 0
    for i in range(10):
        when = NOW + timedelta(minutes=i + 1)
        decisions = await asyncio.gather(
            *(ledger.try_consume(f"race{i}", limits, when, "interactive") for _ in range(calls))
        )
        allowed += sum(d.allowed for d in decisions)
    return allowed


async def test_try_consume_concurrent_first_calls_on_fresh_minute_all_allowed(
    ledger: QuotaLedger, db: Database
) -> None:
    limits = ProviderLimits(per_minute=60, per_day=10_000)

    allowed = await _fresh_window_burst(ledger, limits, 12)

    assert allowed == 120  # a lost insert race must not read as "window full"
    for i in range(10):
        doc = await db["provider_quota"].find_one(
            {"provider": f"race{i}", "window": "minute", "start": {"$gt": NOW}}
        )
        assert doc is not None
        assert doc["used"] == 12


async def test_try_consume_concurrent_calls_above_minute_limit_allow_exactly_the_limit(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=5, per_day=10_000)

    allowed = await _fresh_window_burst(ledger, limits, 12)

    assert allowed == 50


async def test_try_consume_concurrent_first_calls_on_fresh_day_all_allowed(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=1000, per_day=1000)
    allowed = 0
    for i in range(10):
        day = NOW + timedelta(days=i + 1)
        decisions = await asyncio.gather(
            *(ledger.try_consume(f"dayrace{i}", limits, day, "scheduled") for _ in range(12))
        )
        allowed += sum(d.allowed for d in decisions)
        assert all(d.window_blocked is None for d in decisions)  # no refusal, so no false block
        assert (await ledger.snapshot(f"dayrace{i}", limits, day)).used_today == 12

    assert allowed == 120


async def test_try_consume_concurrent_calls_above_day_limit_allow_exactly_the_limit(
    ledger: QuotaLedger, db: Database
) -> None:
    limits = ProviderLimits(per_minute=1000, per_day=5)
    allowed = 0
    for i in range(10):
        day = NOW + timedelta(days=i + 1)
        decisions = await asyncio.gather(
            *(ledger.try_consume(f"daycap{i}", limits, day, "scheduled") for _ in range(12))
        )
        allowed += sum(d.allowed for d in decisions)
        # Day-blocked calls roll their minute increment back, even under concurrency.
        minute_doc = await db["provider_quota"].find_one(
            {"provider": f"daycap{i}", "window": "minute"}
        )
        assert minute_doc is not None
        assert minute_doc["used"] == 5

    assert allowed == 50
