"""Watchlist overview: one summary row per symbol, where one bad symbol never spoils the list."""

import asyncio

from pydantic import BaseModel

from app.logging_setup import get_logger
from app.providers.models import Exchange
from app.services.analysis import AnalysisService
from app.services.errors import AppError
from app.services.market_data import MarketDataService
from app.services.reports import Lean
from app.services.status import State, combine

log = get_logger(__name__)

CONCURRENCY = 4
SPARKLINE_POINTS = 20
WEEK_SESSIONS = 5


class OverviewRow(BaseModel):
    symbol: str
    name: str | None
    exchange: Exchange | None
    currency: str | None
    last_price: float | None
    change_1w_pct: float | None  # last close versus the close 5 sessions earlier, in percent
    sparkline: list[float]  # last 20 daily closes, oldest first
    lean: Lean | None
    status: State
    status_reason: str | None


def _failed(symbol: str, reason: str) -> OverviewRow:
    return OverviewRow(
        symbol=symbol,
        name=None,
        exchange=None,
        currency=None,
        last_price=None,
        change_1w_pct=None,
        sparkline=[],
        lean=None,
        status="unavailable",
        status_reason=reason,
    )


async def _row(market: MarketDataService, analysis: AnalysisService, symbol: str) -> OverviewRow:
    # Bars first, alone: the quote and technical calls below then hit a warm cache instead of
    # racing each other into duplicate vendor fetches.
    frame, price_status = await market.daily_history(symbol)
    quote_result, technical = await asyncio.gather(
        market.quote(symbol), analysis.technical(symbol), return_exceptions=True
    )
    if isinstance(quote_result, BaseException):
        raise quote_result
    quote, quote_status = quote_result
    statuses = [price_status, quote_status]
    lean: Lean | None = None
    if isinstance(technical, AppError):
        log.info("overview_no_outlook", symbol=symbol, reason=technical.message)
    elif isinstance(technical, BaseException):
        raise technical
    else:
        lean = technical.outlook.lean
        statuses.append(technical.data_status.overall)
    closes = [float(c) for c in frame["close"].tolist()]
    change = (
        (closes[-1] / closes[-1 - WEEK_SESSIONS] - 1.0) * 100.0
        if len(closes) > WEEK_SESSIONS and closes[-1 - WEEK_SESSIONS]
        else None
    )
    overall = combine(statuses)
    return OverviewRow(
        symbol=symbol,
        name=quote.name,
        exchange=quote.exchange,
        currency=quote.currency,
        last_price=quote.price,
        change_1w_pct=change,
        sparkline=closes[-SPARKLINE_POINTS:],
        lean=lean,
        status=overall.state,
        status_reason=overall.reason,
    )


async def build_overview(
    market: MarketDataService, analysis: AnalysisService, symbols: list[str]
) -> list[OverviewRow]:
    """Rows in the order of ``symbols``; a failing symbol becomes an "unavailable" row."""
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(symbol: str) -> OverviewRow:
        async with gate:
            try:
                return await _row(market, analysis, symbol)
            except AppError as exc:
                return _failed(symbol, exc.message)
            except Exception:
                log.exception("overview_row_failed", symbol=symbol)
                return _failed(symbol, "Something went wrong loading this stock.")

    return list(await asyncio.gather(*(one(s) for s in symbols)))
