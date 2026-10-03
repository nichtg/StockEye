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

    decisions = await asyncio.gather(*(ledger.try_consume("p", limits, NOW) for _ in range(50)))

    assert sum(d.allowed for d in decisions) == 20
    assert (await ledger.snapshot("p", limits, NOW)).used_today == 20


async def test_try_consume_minute_limit_blocks_then_resets_next_minute(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=2, per_day=100)

    first = [await ledger.try_consume("p", limits, NOW) for _ in range(3)]
    later = await ledger.try_consume("p", limits, NOW + timedelta(minutes=1))

    assert [d.allowed for d in first] == [True, True, False]
    assert first[2].window_blocked == "minute"
    assert first[2].retry_at == datetime(2026, 3, 10, 12, 31, tzinfo=UTC)
    assert later.allowed


async def test_try_consume_day_block_rolls_back_the_minute_increment(
    ledger: QuotaLedger, db: Database
) -> None:
    limits = ProviderLimits(per_minute=10, per_day=2)
    for _ in range(2):
        await ledger.try_consume("p", limits, NOW)

    blocked = await ledger.try_consume("p", limits, NOW)

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
            await ledger.try_consume("alphavantage", limits, NOW)

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
            await ledger.try_consume("p", limits, NOW)

    errors = _events(logs, "provider_quota_exhausted")
    assert len(errors) == 1
    assert errors[0]["log_level"] == "error"


async def test_try_consume_logs_one_throttle_warning_per_minute_window(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=1, per_day=100)

    with capture_logs() as logs:
        for _ in range(4):
            await ledger.try_consume("p", limits, NOW)
        await ledger.try_consume("p", limits, NOW + timedelta(minutes=1))
        await ledger.try_consume("p", limits, NOW + timedelta(minutes=1))

    assert len(_events(logs, "provider_rate_throttled")) == 2


async def test_try_consume_logs_reset_when_new_day_follows_a_warned_day(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=100, per_day=5)
    for _ in range(4):
        await ledger.try_consume("p", limits, NOW)

    with capture_logs() as logs:
        await ledger.try_consume("p", limits, NOW + timedelta(days=1))
        await ledger.try_consume("p", limits, NOW + timedelta(days=1))

    assert len(_events(logs, "provider_quota_reset")) == 1


async def test_try_consume_no_reset_log_when_previous_day_was_quiet(
    ledger: QuotaLedger,
) -> None:
    limits = ProviderLimits(per_minute=100, per_day=50)
    await ledger.try_consume("p", limits, NOW)

    with capture_logs() as logs:
        await ledger.try_consume("p", limits, NOW + timedelta(days=1))

    assert _events(logs, "provider_quota_reset") == []


async def test_snapshot_reports_usage_and_next_utc_midnight(ledger: QuotaLedger) -> None:
    limits = ProviderLimits(per_minute=100, per_day=50)
    await ledger.try_consume("p", limits, NOW)

    snap = await ledger.snapshot("p", limits, NOW)

    assert (snap.used_today, snap.daily_limit) == (1, 50)
    assert snap.resets_at == datetime(2026, 3, 11, tzinfo=UTC)


async def test_record_error_round_trips_latest_error(ledger: QuotaLedger) -> None:
    assert await ledger.last_error("p") is None

    await ledger.record_error("p", "first", NOW)
    await ledger.record_error("p", "second", NOW + timedelta(seconds=5))

    assert await ledger.last_error("p") == ("second", NOW + timedelta(seconds=5))
