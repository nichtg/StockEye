from datetime import datetime, timedelta

import pytest
from bson import ObjectId

from app.db import Database
from app.jobs.ingest import refresh_exchange
from app.jobs.scheduler import build_scheduler, schedule_startup_discover
from app.providers.errors import RateLimitedError, TransientProviderError
from app.providers.models import Bar, Interval
from app.providers.quota import current_priority
from app.repositories.cache import CacheRepository
from app.repositories.watchlists import WatchlistsRepository
from app.services.container import Services
from app.services.overview import build_overview
from tests.services.fakes import CLOSED_NOW, FakeClock, FakeMarketData

pytestmark = pytest.mark.integration


async def test_overview_returns_one_complete_row_per_symbol(services: Services) -> None:
    rows = await build_overview(services.market, services.analysis, ["AAPL", "D05.SI"])

    assert [r.symbol for r in rows] == ["AAPL", "D05.SI"]
    aapl, dbs = rows
    assert aapl.status == "ok"
    assert aapl.exchange == "US"
    assert aapl.currency == "USD"
    assert aapl.name == "Apple Inc."
    assert aapl.last_price is not None
    assert len(aapl.sparkline) == 20
    assert aapl.lean in {"bullish", "bearish", "neutral"}
    assert dbs.exchange == "SGX"
    assert dbs.currency == "SGD"


async def test_overview_change_is_last_close_versus_five_sessions_earlier(
    services: Services,
) -> None:
    (row,) = await build_overview(services.market, services.analysis, ["AAPL"])

    frame, _ = await services.market.daily_history("AAPL")
    expected = (frame["close"].iloc[-1] / frame["close"].iloc[-6] - 1.0) * 100.0
    assert row.change_1w_pct == pytest.approx(expected)
    assert row.sparkline[-1] == pytest.approx(frame["close"].iloc[-1])


async def test_overview_one_failing_symbol_does_not_fail_the_list(
    services: Services, provider: FakeMarketData
) -> None:
    provider.fail_symbols["MSFT"] = TransientProviderError("yahoo", "down")

    rows = await build_overview(services.market, services.analysis, ["AAPL", "MSFT", "ZZZZ"])

    by_symbol = {r.symbol: r for r in rows}
    assert by_symbol["AAPL"].status == "ok"
    for bad in ("MSFT", "ZZZZ"):
        row = by_symbol[bad]
        assert row.status == "unavailable"
        assert row.status_reason
        assert row.last_price is None
        assert row.lean is None
        assert row.sparkline == []


async def test_overview_empty_watchlist_returns_empty_list(services: Services) -> None:
    assert await build_overview(services.market, services.analysis, []) == []


async def test_watchlist_all_symbols_is_distinct_and_sorted(db: Database) -> None:
    repo = WatchlistsRepository(db)
    await repo.add(ObjectId(), "MSFT", 50)
    one, two = ObjectId(), ObjectId()
    await repo.add(one, "AAPL", 50)
    await repo.add(two, "AAPL", 50)
    await repo.add(two, "D05.SI", 50)

    assert await repo.all_symbols() == ["AAPL", "D05.SI", "MSFT"]


async def test_refresh_job_only_touches_symbols_of_its_exchange_and_counts_failures(
    services: Services, db: Database, provider: FakeMarketData
) -> None:
    repo = WatchlistsRepository(db)
    owner = ObjectId()
    for symbol in ("AAPL", "MSFT", "D05.SI"):
        await repo.add(owner, symbol, 50)
        assert await services.admission.admit(owner, symbol)
    provider.fail_symbols["MSFT"] = TransientProviderError("yahoo", "down")

    summary = await refresh_exchange(services, db, "US")

    assert summary.symbols == 2
    assert summary.failures == 1
    assert provider.calls["bars"] >= 1
    assert await services.news.progress("AAPL") is not None
    assert (await services.news.progress("AAPL")).months_done == 24
    assert (await services.news.progress("D05.SI")).months_done == 0  # other exchange untouched


async def test_refresh_job_makes_its_vendor_calls_as_scheduled_work(
    services: Services, db: Database, provider: FakeMarketData
) -> None:
    await WatchlistsRepository(db).add(ObjectId(), "AAPL", 50)
    seen: list[str] = []
    real_bars = provider.bars

    async def spying_bars(
        symbol: str, interval: Interval, start: datetime, end: datetime
    ) -> list[Bar]:
        seen.append(current_priority())
        return await real_bars(symbol, interval, start, end)

    provider.bars = spying_bars  # type: ignore[method-assign]  # test spy

    await refresh_exchange(services, db, "US")
    await services.market.daily_history("MSFT")  # a user-driven call afterwards

    assert seen == ["scheduled", "interactive"]


async def test_scheduler_has_one_weekday_job_per_exchange(services: Services, db: Database) -> None:
    scheduler = build_scheduler(services, db)

    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert set(jobs) == {"refresh_us", "refresh_sgx", "discover_refresh", "prune_market_data"}
    assert "21" in str(jobs["refresh_us"].trigger)
    assert "mon-fri" in str(jobs["refresh_sgx"].trigger)
    discover = jobs["discover_refresh"]
    assert "mon-fri" in str(discover.trigger)
    assert "hour='22'" in str(discover.trigger)
    assert "minute='30'" in str(discover.trigger)
    assert discover.max_instances == 1
    assert discover.coalesce
    prune = str(jobs["prune_market_data"].trigger)
    assert "day_of_week='sun'" in prune
    assert "hour='3'" in prune


async def test_startup_discover_build_is_scheduled_only_when_nothing_is_stored(
    services: Services, db: Database, provider: FakeMarketData
) -> None:
    provider.screen_hits = {"us": ["AAPL"], "sg": []}
    scheduler = build_scheduler(services, db)

    assert await schedule_startup_discover(scheduler, services)
    job = scheduler.get_job("discover_startup")
    assert job is not None
    assert "date" in str(job.trigger)
    assert provider.calls["screen"] == 0  # scheduled for later, never run inline

    scheduler.remove_job("discover_startup")
    await services.discover.refresh()

    assert not await schedule_startup_discover(scheduler, services)
    assert scheduler.get_job("discover_startup") is None


async def test_startup_discover_build_is_skipped_after_a_recent_attempt_with_no_page(
    services: Services, db: Database
) -> None:
    await services.discover.refresh()
    await db["analysis_cache"].delete_one({"key": "discover:v2"})  # crashed before it was saved
    scheduler = build_scheduler(services, db)

    assert not await schedule_startup_discover(scheduler, services)
    assert scheduler.get_job("discover_startup") is None


async def test_cache_lookup_returns_expired_entry_marked_not_fresh(db: Database) -> None:
    cache = CacheRepository(db)
    await cache.put("k", {"v": 1}, timedelta(minutes=1), CLOSED_NOW)

    entry = await cache.lookup("k")

    assert entry is not None
    assert entry.payload == {"v": 1}
    assert entry.is_fresh(CLOSED_NOW)
    assert not entry.is_fresh(CLOSED_NOW + timedelta(hours=1))
    assert await cache.lookup("missing") is None


async def test_overview_row_carries_country_sector_and_market_cap(services: Services) -> None:
    aapl, dbs = await build_overview(services.market, services.analysis, ["AAPL", "D05.SI"])

    assert (aapl.country, aapl.sector, aapl.market_cap) == ("United States", "Technology", 2.5e9)
    assert dbs.country == "Singapore"


async def test_overview_failing_profile_still_gives_an_ok_row_with_empty_fields(
    services: Services, provider: FakeMarketData
) -> None:
    provider.profile_fail = TransientProviderError("yahoo", "down")

    (row,) = await build_overview(services.market, services.analysis, ["AAPL"])

    assert row.status == "ok"
    assert row.last_price is not None
    assert (row.country, row.sector, row.market_cap) == (None, None, None)


async def test_overview_ok_row_has_no_status_as_of(services: Services) -> None:
    (row,) = await build_overview(services.market, services.analysis, ["AAPL"])

    assert row.status == "ok"
    assert row.status_as_of is None


async def test_overview_stale_quote_row_reports_when_the_saved_quote_was_fetched(
    services: Services, clock: FakeClock, provider: FakeMarketData
) -> None:
    quote, _ = await services.market.quote("AAPL")
    await services.market.daily_history("AAPL")
    clock.now = CLOSED_NOW + timedelta(hours=2)
    provider.fail_with = RateLimitedError("yahoo")

    (row,) = await build_overview(services.market, services.analysis, ["AAPL"])

    assert row.status != "ok"
    assert row.status_as_of == quote.as_of


async def test_overview_failed_row_has_no_status_as_of(
    services: Services, provider: FakeMarketData
) -> None:
    provider.fail_symbols["MSFT"] = TransientProviderError("yahoo", "down")

    (row,) = await build_overview(services.market, services.analysis, ["MSFT"])

    assert row.status == "unavailable"
    assert row.status_as_of is None
