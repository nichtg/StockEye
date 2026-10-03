from datetime import UTC, date, datetime, timedelta

import pytest

from app.db import Database
from app.providers.errors import RateLimitedError, TransientProviderError
from app.providers.models import Bar
from app.repositories.bars import BarsRepository
from app.services.container import Services
from app.services.errors import AppError
from tests.services.fakes import CLOSED_NOW, OPEN_NOW, FakeClock, FakeMarketData

pytestmark = pytest.mark.integration


async def test_daily_history_second_call_is_served_from_cache(
    services: Services, provider: FakeMarketData
) -> None:
    await services.market.daily_history("AAPL")
    await services.market.daily_history("AAPL")

    assert provider.calls["bars"] == 1


async def test_daily_history_returns_domain_convention_frame(services: Services) -> None:
    frame, status = await services.market.daily_history("AAPL")

    assert status.state == "ok"
    assert frame.index.tz is None
    assert frame.index.is_monotonic_increasing
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.index[-1].date() == date(2026, 10, 2)  # last completed session
    assert str(frame["close"].dtype) == "float64"


async def test_daily_history_drops_in_progress_bar_while_market_open(
    services: Services, clock: FakeClock, provider: FakeMarketData
) -> None:
    clock.now = OPEN_NOW  # Friday mid-session: the provider includes Friday's partial bar

    frame, _ = await services.market.daily_history("AAPL")

    assert provider.calls["bars"] == 1
    assert frame.index[-1].date() == date(2026, 10, 1)


async def test_daily_history_refetches_after_close_to_pick_up_final_bar(
    services: Services, clock: FakeClock, provider: FakeMarketData
) -> None:
    clock.now = OPEN_NOW
    await services.market.daily_history("AAPL")
    clock.now = OPEN_NOW.replace(hour=21)  # after the 20:00 UTC close

    frame, _ = await services.market.daily_history("AAPL")

    assert provider.calls["bars"] == 2
    assert frame.index[-1].date() == date(2026, 10, 2)


async def test_hourly_history_drops_hour_still_forming(
    services: Services, clock: FakeClock
) -> None:
    clock.now = OPEN_NOW.replace(minute=30)  # 15:30 UTC: the 15:00 UTC bar is still forming

    frame, _ = await services.market.hourly_history("AAPL")

    # Bars start at 13:00, 14:00 and 15:00 UTC today; only the first two have finished.
    today_bars = [ts for ts in frame.index if ts.date() == date(2026, 10, 2)]
    assert [ts.hour for ts in today_bars] == [9, 10]  # exchange-local (EDT = UTC-4)
    assert frame.index.tz is None


async def test_hourly_history_uses_exchange_local_timestamps(services: Services) -> None:
    frame, _ = await services.market.hourly_history("AAPL")

    # Fake bars end at the NYSE close (20:00 UTC = 16:00 EDT); last bar starts 15:00 local.
    assert frame.index[-1].hour == 15


async def test_daily_history_provider_rate_limited_serves_stale_cache(
    services: Services, clock: FakeClock, provider: FakeMarketData
) -> None:
    await services.market.daily_history("AAPL")
    clock.now = CLOSED_NOW + timedelta(days=4, hours=3)  # new sessions exist; cache is behind
    provider.fail_with = RateLimitedError("yahoo")

    frame, status = await services.market.daily_history("AAPL")

    assert status.state == "stale"
    assert status.reason is not None
    assert "Yahoo Finance hit its rate limit" in status.reason
    assert "Showing the last saved prices" in status.reason
    assert len(frame) > 100


async def test_daily_history_nothing_cached_and_provider_down_raises_503(
    services: Services, provider: FakeMarketData
) -> None:
    provider.fail_with = TransientProviderError("yahoo", "boom")

    with pytest.raises(AppError) as caught:
        await services.market.daily_history("AAPL")

    assert caught.value.status == 503
    assert caught.value.code == "data_unavailable"
    assert "AAPL" in caught.value.message


async def test_daily_history_unknown_symbol_raises_404(services: Services) -> None:
    with pytest.raises(AppError) as caught:
        await services.market.daily_history("ZZZZ")

    assert caught.value.status == 404
    assert caught.value.code == "not_found"


async def test_quote_is_cached_for_sixty_seconds(
    services: Services, clock: FakeClock, provider: FakeMarketData
) -> None:
    await services.market.quote("AAPL")
    clock.now = CLOSED_NOW + timedelta(seconds=30)
    await services.market.quote("AAPL")
    assert provider.calls["quote"] == 1

    clock.now = CLOSED_NOW + timedelta(seconds=61)
    await services.market.quote("AAPL")

    assert provider.calls["quote"] == 2


async def test_quote_falls_back_to_stale_copy_when_provider_fails(
    services: Services, clock: FakeClock, provider: FakeMarketData
) -> None:
    await services.market.quote("AAPL")
    clock.now = CLOSED_NOW + timedelta(hours=2)
    provider.fail_with = RateLimitedError("yahoo")

    quote, status = await services.market.quote("AAPL")

    assert quote.symbol == "AAPL"
    assert status.state == "stale"
    assert status.reason is not None
    assert "2 hours old" in status.reason


async def test_search_shorter_than_one_character_returns_empty_without_provider_call(
    services: Services, provider: FakeMarketData
) -> None:
    assert await services.market.search("") == []
    assert await services.market.search("   ") == []
    assert provider.calls["search"] == 0


async def test_search_results_are_cached(services: Services, provider: FakeMarketData) -> None:
    first = await services.market.search("dbs")
    second = await services.market.search("DBS")

    assert [m.symbol for m in first] == ["D05.SI"]
    assert second == first
    assert provider.calls["search"] == 1


async def test_events_stale_fallback_keeps_saved_events(
    services: Services, clock: FakeClock, provider: FakeMarketData
) -> None:
    start, end = date(2025, 1, 1), date(2026, 10, 2)
    saved, _ = await services.market.events("AAPL", start, end)
    clock.now = CLOSED_NOW + timedelta(days=2)
    provider.fail_with = RateLimitedError("yahoo")

    events, status = await services.market.events("AAPL", start, end)

    assert events == saved
    assert saved
    assert status.state == "stale"


async def test_events_without_cache_and_provider_down_is_unavailable_not_error(
    services: Services, provider: FakeMarketData
) -> None:
    provider.fail_with = RateLimitedError("yahoo")

    events, status = await services.market.events("AAPL", date(2025, 1, 1), date(2026, 10, 2))

    assert events == []
    assert status.state == "unavailable"


async def test_bars_replace_range_swaps_in_range_bars_and_widens_coverage(db: Database) -> None:
    repo = BarsRepository(db)
    day = datetime(2026, 9, 1, tzinfo=UTC)

    def bar(offset: int, close: float) -> Bar:
        ts = day + timedelta(days=offset)
        return Bar(ts=ts, open=close, high=close, low=close, close=close, volume=1.0)

    await repo.replace_range(
        "AAPL",
        "1d",
        [bar(0, 1.0), bar(1, 2.0)],
        start=day,
        end=day + timedelta(days=5),
        fetched_at=day,
    )
    state = await repo.replace_range(
        "AAPL",
        "1d",
        [bar(1, 3.0)],
        start=day - timedelta(days=9),
        end=day + timedelta(days=5),
        fetched_at=day + timedelta(days=2),
    )

    stored = await repo.get_range("AAPL", "1d", day - timedelta(days=10), day + timedelta(days=10))
    assert [b.close for b in stored] == [3.0]
    assert state.covered_start == day - timedelta(days=9)
    assert state.last_bar_at == day + timedelta(days=1)
