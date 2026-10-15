"""Weekly clean-up: drop saved prices of stocks nobody follows any more.

Discover rotates through new stocks every night, and each one leaves about three years of daily
bars behind. A stock is pruned only when it is on no watchlist, is not on the current Discover
page and has not been fetched for two weeks; anyone who looks at it again simply refetches it.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.clock import utc_now
from app.db import Database
from app.logging_setup import get_logger
from app.repositories.bars import BarsRepository
from app.repositories.events import EventsRepository
from app.repositories.watchlists import WatchlistsRepository
from app.services.container import Services

log = get_logger(__name__)

IDLE_FOR = timedelta(days=14)


@dataclass(frozen=True)
class PruneSummary:
    symbols: int
    bars: int
    events: int


async def prune_orphan_market_data(
    services: Services, db: Database, now: datetime | None = None
) -> PruneSummary:
    """Delete bars and events of idle, unreferenced symbols. Never raises; logs the counts."""
    try:
        cutoff = (now or utc_now()) - IDLE_FOR
        bars, events = BarsRepository(db), EventsRepository(db)
        keep = set(await WatchlistsRepository(db).all_symbols())
        keep |= await services.discover.current_symbols()
        orphans = [s for s in await bars.idle_symbols(cutoff) if s not in keep]
        bar_count = event_count = 0
        for symbol in orphans:
            bar_count += await bars.delete_symbol(symbol)
            event_count += await events.delete_symbol(symbol)
    except Exception:
        log.exception("prune_job_failed")
        return PruneSummary(0, 0, 0)
    log.info("prune_job_finished", symbols=len(orphans), bars=bar_count, events=event_count)
    return PruneSummary(len(orphans), bar_count, event_count)
