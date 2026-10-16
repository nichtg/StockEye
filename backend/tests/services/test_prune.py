from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.db import Database
from app.jobs.prune import months_before, prune_orphan_market_data
from app.repositories.bars import BarsRepository
from app.repositories.events import EventsRepository
from app.repositories.news import ARTICLES, STATE, NewsRepository
from app.repositories.watchlists import WatchlistsRepository
from app.services.container import Services
from tests.services.fakes import FakeClock, FakeMarketData
from tests.services.test_news_feed import seed

pytestmark = pytest.mark.integration


async def _has_bars(db: Database, symbol: str) -> bool:
    return await BarsRepository(db).get_state(symbol, "1d") is not None


async def test_prune_removes_only_old_orphans(
    services: Services, db: Database, provider: FakeMarketData, clock: FakeClock
) -> None:
    await WatchlistsRepository(db).add(ObjectId(), "AAPL", 50)
    provider.screen_hits = {"us": ["MSFT"], "sg": []}
    for symbol in ("AAPL", "TSLA"):  # one watchlisted, one orphan
        await services.market.daily_history(symbol)
        await services.market.standard_events(symbol)
    await services.discover.refresh()  # puts MSFT on the Discover page and saves its bars
    clock.now += timedelta(days=20)
    await services.market.daily_history("NVDA")  # an orphan, but fetched just now

    summary = await prune_orphan_market_data(services, db, clock.now)

    assert summary.symbols == 1
    assert summary.bars > 0
    assert summary.events > 0
    assert not await _has_bars(db, "TSLA")
    assert await EventsRepository(db).get_state("TSLA") is None
    assert await _has_bars(db, "AAPL")  # on a watchlist
    assert await _has_bars(db, "MSFT")  # on the current Discover page
    assert await _has_bars(db, "NVDA")  # fetched recently


async def test_prune_keeps_orphans_idle_for_less_than_two_weeks(
    services: Services, db: Database, clock: FakeClock
) -> None:
    await services.market.daily_history("TSLA")
    clock.now += timedelta(days=13)

    summary = await prune_orphan_market_data(services, db, clock.now)

    assert summary.symbols == 0
    assert await _has_bars(db, "TSLA")


def test_months_before_clamps_the_day_to_the_target_month() -> None:
    assert months_before(datetime(2026, 10, 3, 12, tzinfo=UTC), 25) == datetime(
        2024, 9, 3, 12, tzinfo=UTC
    )
    assert months_before(datetime(2026, 3, 31, tzinfo=UTC), 1) == datetime(2026, 2, 28, tzinfo=UTC)
    assert months_before(datetime(2026, 1, 15, tzinfo=UTC), 2) == datetime(2025, 11, 15, tzinfo=UTC)


async def test_prune_deletes_news_older_than_25_months_for_every_symbol(
    services: Services, db: Database, clock: FakeClock
) -> None:
    cutoff = months_before(clock.now, 25)
    await seed(db, "AAPL", "Apple too old", cutoff - timedelta(days=1))  # 25 months and a day
    await seed(db, "MSFT", "Microsoft too old", cutoff - timedelta(days=90))
    await seed(db, "AAPL", "Apple just inside", cutoff + timedelta(days=1))  # 24 months, 29 days
    await seed(db, "AAPL", "Apple recent", clock.now - timedelta(days=2))
    await db[STATE].insert_one({"symbol": "AAPL", "backfilled_months": ["2024-01"]})
    await services.market.daily_history("AAPL")

    summary = await prune_orphan_market_data(services, db, clock.now)

    assert summary.articles == 2
    titles = sorted([d["title"] async for d in db[ARTICLES].find({})])
    assert titles == ["Apple just inside", "Apple recent"]
    assert await db[STATE].count_documents({}) == 1  # other collections untouched
    assert await _has_bars(db, "AAPL")


async def test_prune_news_failure_is_logged_not_raised(
    services: Services, db: Database, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_args: object) -> int:
        raise RuntimeError("mongo down")

    monkeypatch.setattr(NewsRepository, "delete_published_before", boom)

    summary = await prune_orphan_market_data(services, db, clock.now)

    assert summary.articles == 0
