"""Weekly clean-up: drop saved prices of stocks nobody follows any more, and old news.

Discover rotates through new stocks every night, and each one leaves about three years of daily
bars behind. A stock is pruned only when it is on no watchlist, is not on the current Discover
page and has not been fetched for two weeks; anyone who looks at it again simply refetches it.

News is trimmed by date alone: articles older than 25 months go, for every symbol (the macro
study reads 24 months, so the extra month is slack for the window edge).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.clock import utc_now
from app.db import Database
from app.domain.calendar_months import months_before
from app.logging_setup import get_logger
from app.repositories.bars import BarsRepository
from app.repositories.events import EventsRepository
from app.repositories.news_maintenance import NewsMaintenanceRepository
from app.repositories.watchlists import WatchlistsRepository
from app.services.container import Services

log = get_logger(__name__)

IDLE_FOR = timedelta(days=14)
NEWS_RETENTION_MONTHS = 25


@dataclass(frozen=True)
class PruneSummary:
    symbols: int
    bars: int
    events: int
    articles: int = 0  # news articles older than the retention window


async def prune_orphan_market_data(
    services: Services, db: Database, now: datetime | None = None
) -> PruneSummary:
    """Delete idle symbols' bars and events, and news past retention. Never raises; logs counts.

    The two halves are independent: a failure in one is logged and the other still runs.
    """
    now = now or utc_now()
    symbols = bar_count = event_count = 0
    try:
        bars, events = BarsRepository(db), EventsRepository(db)
        keep = set(await WatchlistsRepository(db).all_symbols())
        keep |= await services.discover.current_symbols()
        orphans = [s for s in await bars.idle_symbols(now - IDLE_FOR) if s not in keep]
        for symbol in orphans:
            bar_count += await bars.delete_symbol(symbol)
            event_count += await events.delete_symbol(symbol)
        symbols = len(orphans)
    except Exception:
        log.exception("prune_job_failed")
    articles = 0
    try:
        cutoff = months_before(now, NEWS_RETENTION_MONTHS)
        articles = await NewsMaintenanceRepository(db).delete_published_before(cutoff)
    except Exception:
        log.exception("prune_news_failed")
    log.info(
        "prune_job_finished", symbols=symbols, bars=bar_count, events=event_count, articles=articles
    )
    return PruneSummary(symbols, bar_count, event_count, articles)
