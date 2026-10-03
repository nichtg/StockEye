"""One vendor call per series however many callers ask at once, duplicates or not."""

import asyncio
from datetime import timedelta

import pytest
from bson import ObjectId

from app.db import Database
from app.repositories.cache import CacheRepository
from app.services.analysis import macro_cache_key
from app.services.container import Services
from app.services.errors import AppError
from app.services.market_data import MarketDataService
from tests.services.fakes import CLOSED_NOW, FakeClock, FakeMarketData

pytestmark = pytest.mark.integration


class TickingClock(FakeClock):
    """Advances on every read, so a caller-derived window would differ between callers."""

    def __call__(self):  # type: ignore[no-untyped-def]
        self.now = self.now + timedelta(microseconds=1)
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return TickingClock(CLOSED_NOW)


async def _timestamps(db: Database, interval: str) -> list[object]:
    docs = db["price_bars"].find({"meta.symbol": "AAPL", "meta.interval": interval})
    return [d["ts"] async for d in docs]


async def test_hourly_history_concurrent_calls_make_one_vendor_call_and_no_duplicates(
    services: Services, provider: FakeMarketData, db: Database
) -> None:
    await asyncio.gather(*(services.market.hourly_history("AAPL") for _ in range(3)))

    stamps = await _timestamps(db, "1h")
    assert provider.calls["bars"] == 1
    assert stamps
    assert len(stamps) == len(set(stamps))


async def test_daily_history_concurrent_calls_make_one_vendor_call_and_no_duplicates(
    services: Services, provider: FakeMarketData, db: Database
) -> None:
    await asyncio.gather(*(services.market.daily_history("AAPL") for _ in range(3)))

    stamps = await _timestamps(db, "1d")
    assert provider.calls["bars"] == 1
    assert len(stamps) == len(set(stamps))


async def test_standard_events_concurrent_calls_make_one_vendor_call(
    services: Services, provider: FakeMarketData
) -> None:
    await asyncio.gather(*(services.market.standard_events("AAPL") for _ in range(3)))

    assert provider.calls["events"] == 1


async def test_quote_concurrent_calls_make_one_vendor_call(
    services: Services, provider: FakeMarketData
) -> None:
    await asyncio.gather(*(services.market.quote("AAPL") for _ in range(3)))

    assert provider.calls["quote"] == 1


async def test_search_concurrent_calls_make_one_vendor_call(
    services: Services, provider: FakeMarketData
) -> None:
    await asyncio.gather(*(services.market.search("apple") for _ in range(3)))

    assert provider.calls["search"] == 1


class DuplicatingVendor(FakeMarketData):
    """A vendor that repeats the newest bar in every answer."""

    async def bars(self, symbol, interval, start, end):  # type: ignore[no-untyped-def]
        fetched = await super().bars(symbol, interval, start, end)
        return fetched + fetched[-1:]


async def test_vendor_duplicate_timestamps_are_stored_once(clock: FakeClock, db: Database) -> None:
    market = MarketDataService(db, DuplicatingVendor(clock), clock)

    await market.daily_history("AAPL")

    stamps = await _timestamps(db, "1d")
    assert stamps
    assert len(stamps) == len(set(stamps))


async def test_vendor_duplicates_do_not_cause_refetches(clock: FakeClock, db: Database) -> None:
    vendor = DuplicatingVendor(clock)
    market = MarketDataService(db, vendor, clock)

    for _ in range(5):
        await market.daily_history("AAPL")

    assert vendor.calls["bars"] == 1


async def test_fetch_state_without_bars_in_the_window_neither_loops_nor_fails_with_503(
    services: Services, provider: FakeMarketData, db: Database
) -> None:
    await services.market.daily_history("AAPL")
    await db["price_bars"].delete_many({})  # the state still says there is a newest bar
    calls_before = provider.calls["bars"]

    for _ in range(3):
        try:
            await services.market.daily_history("AAPL")
        except AppError as exc:
            assert exc.status != 503

    assert provider.calls["bars"] - calls_before <= 1


async def test_macro_with_an_old_shape_cache_entry_recomputes_instead_of_failing(
    services: Services, db: Database
) -> None:
    old_shape = {"symbol": "AAPL", "report": {"top_events": "from an older build"}}
    await CacheRepository(db).put(
        macro_cache_key("AAPL"), old_shape, timedelta(hours=1), CLOSED_NOW
    )

    response = await services.analysis.macro("AAPL", ObjectId())

    assert response.symbol == "AAPL"
