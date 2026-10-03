"""Watchlist overview: one summary row per symbol, where one bad symbol never spoils the list."""

import asyncio

from pydantic import BaseModel

from app.domain.technical.outlook import Lean
from app.logging_setup import get_logger
from app.providers.models import Exchange
from app.services.analysis import AnalysisService
from app.services.errors import AppError
from app.services.market_data import MarketDataService
from app.services.reports import TechnicalReport
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


async def _outlook(analysis: AnalysisService, symbol: str) -> TechnicalReport | None:
    """The technical report, or None when there is too little history for one."""
    try:
        return await analysis.technical(symbol)
    except AppError as exc:
        log.info("overview_no_outlook", symbol=symbol, reason=exc.message)
        return None


async def _row(market: MarketDataService, analysis: AnalysisService, symbol: str) -> OverviewRow:
    (frame, price_status), (quote, quote_status), technical = await asyncio.gather(
        market.daily_history(symbol), market.quote(symbol), _outlook(analysis, symbol)
    )
    statuses = [price_status, quote_status]
    lean: Lean | None = None
    if technical is not None:
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
