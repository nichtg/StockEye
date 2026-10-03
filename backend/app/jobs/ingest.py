"""Scheduled refresh: bring watchlisted symbols up to date after each exchange's close."""

import asyncio
from dataclasses import dataclass

from app.db import Database
from app.logging_setup import get_logger
from app.providers.models import Exchange
from app.providers.quota import scheduled_calls
from app.repositories.watchlists import WatchlistsRepository
from app.services.calendars import exchange_for
from app.services.container import Services

log = get_logger(__name__)


@dataclass(frozen=True)
class RefreshSummary:
    exchange: Exchange
    symbols: int
    failures: int


async def refresh_exchange(services: Services, db: Database, exchange: Exchange) -> RefreshSummary:
    """Refresh daily bars, events and news for the distinct watchlisted symbols of ``exchange``.

    Never raises: a failing symbol is logged and counted, and the rest carry on. Its vendor calls
    (and those of the ingestion tasks it starts) draw on the quota reserved for scheduled work.
    """
    with scheduled_calls():
        return await _refresh_all(services, db, exchange)


async def _refresh_all(services: Services, db: Database, exchange: Exchange) -> RefreshSummary:
    try:
        everything = await WatchlistsRepository(db).all_symbols()
    except Exception:
        log.exception("refresh_job_symbols_failed", exchange=exchange)
        return RefreshSummary(exchange, 0, 1)
    symbols = [s for s in everything if exchange_for(s) == exchange]
    log.info("refresh_job_started", exchange=exchange, symbols=len(symbols))
    failures = 0
    for symbol in symbols:
        try:
            await _refresh_symbol(services, symbol)
        except Exception:
            failures += 1
            log.exception("refresh_job_symbol_failed", exchange=exchange, symbol=symbol)
    log.info("refresh_job_finished", exchange=exchange, symbols=len(symbols), failures=failures)
    return RefreshSummary(exchange, len(symbols), failures)


async def _refresh_symbol(services: Services, symbol: str) -> None:
    market = services.market
    _, _, name = await asyncio.gather(
        market.daily_history(symbol), market.standard_events(symbol), market.company_name(symbol)
    )
    await services.news.ensure_ingested(symbol, name)
    await services.news.wait(symbol)
