from datetime import timedelta

import pytest
from bson import ObjectId

from app.db import Database
from app.jobs.prune import prune_orphan_market_data
from app.repositories.bars import BarsRepository
from app.repositories.events import EventsRepository
from app.repositories.watchlists import WatchlistsRepository
from app.services.container import Services
from tests.services.fakes import FakeClock, FakeMarketData

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
