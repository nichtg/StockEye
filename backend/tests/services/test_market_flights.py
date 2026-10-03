"""One vendor call per series however many callers ask at once, and self-healing saved data."""

import asyncio
from datetime import timedelta

import pytest
from bson import ObjectId

from app.db import Database
from app.repositories.cache import CacheRepository
from app.services.analysis import macro_cache_key
from app.services.container import Services
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


async def test_duplicated_saved_bars_heal_with_one_refetch(
    services: Services, provider: FakeMarketData, db: Database
) -> None:
    first, _ = await services.market.daily_history("AAPL")
    doc = await db["price_bars"].find_one({"meta.symbol": "AAPL", "meta.interval": "1d"})
    assert doc is not None
    del doc["_id"]
    await db["price_bars"].insert_many([dict(doc), dict(doc)])  # damage: repeated timestamps
    calls_before = provider.calls["bars"]

    healed, status = await services.market.daily_history("AAPL")

    stamps = await _timestamps(db, "1d")
    assert provider.calls["bars"] == calls_before + 1
    assert len(stamps) == len(set(stamps))
    assert status.state == "ok"
    assert healed.equals(first)


async def test_damaged_history_with_the_vendor_down_is_served_as_stale(
    services: Services, provider: FakeMarketData, db: Database
) -> None:
    await services.market.daily_history("AAPL")
    doc = await db["price_bars"].find_one({"meta.symbol": "AAPL", "meta.interval": "1d"})
    assert doc is not None
    del doc["_id"]
    await db["price_bars"].insert_one(doc)
    from app.providers.errors import RateLimitedError  # noqa: PLC0415

    provider.fail_with = RateLimitedError("yahoo")

    frame, status = await services.market.daily_history("AAPL")

    assert not frame.empty
    assert status.state == "stale"


async def test_macro_with_an_old_shape_cache_entry_recomputes_instead_of_failing(
    services: Services, db: Database
) -> None:
    old_shape = {"symbol": "AAPL", "report": {"top_events": "from an older build"}}
    await CacheRepository(db).put(
        macro_cache_key("AAPL"), old_shape, timedelta(hours=1), CLOSED_NOW
    )

    response = await services.analysis.macro("AAPL", ObjectId())

    assert response.symbol == "AAPL"
