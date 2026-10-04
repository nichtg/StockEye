"""Stock data and analysis endpoints (authenticated)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel

from app.api.deps import UserDep
from app.api.limits import MACRO, SEARCH, STOCK, limited
from app.providers.models import Exchange, SymbolMatch
from app.services.container import ServicesDep
from app.services.reports import (
    ChartData,
    MacroResponse,
    NewsProgressOut,
    RangeKey,
    TechnicalReport,
)
from app.services.status import DataStatus

router = APIRouter(prefix="/stocks", tags=["stocks"])

SYMBOL_PATTERN = r"^[A-Z0-9^][A-Z0-9.\-^]{0,14}$"
SymbolPath = Annotated[
    str,
    Path(pattern=SYMBOL_PATTERN, description="Uppercase Yahoo-style ticker, e.g. AAPL or D05.SI"),
]


class StockOut(BaseModel):
    symbol: str
    name: str
    exchange: Exchange
    currency: str
    price: float
    previous_close: float
    change_pct: float | None  # today's move versus the previous close, in percent
    as_of: datetime
    data_status: DataStatus


@router.get("/search", dependencies=[Depends(limited(SEARCH))])
async def search(
    _user: UserDep, services: ServicesDep, q: Annotated[str, Query(max_length=60)] = ""
) -> list[SymbolMatch]:
    return await services.market.search(q)


@router.get("/{symbol}", dependencies=[Depends(limited(STOCK))])
async def stock(symbol: SymbolPath, _user: UserDep, services: ServicesDep) -> StockOut:
    quote, status = await services.market.quote(symbol)
    return StockOut(
        symbol=quote.symbol,
        name=quote.name,
        exchange=quote.exchange,
        currency=quote.currency,
        price=quote.price,
        previous_close=quote.previous_close,
        change_pct=quote.change_pct,
        as_of=quote.as_of,
        data_status=status,
    )


@router.get("/{symbol}/chart", dependencies=[Depends(limited(STOCK))])
async def chart(
    symbol: SymbolPath,
    _user: UserDep,
    services: ServicesDep,
    range: Annotated[RangeKey, Query()] = "6M",
    indicators: Annotated[
        str, Query(description="Comma-separated: sma20,sma50,ema9,ema21,vwap,bollinger,rsi,macd")
    ] = "",
) -> ChartData:
    names = [i.strip().lower() for i in indicators.split(",") if i.strip()]
    return await services.analysis.chart(symbol, range, names)


@router.get("/{symbol}/technical", dependencies=[Depends(limited(STOCK))])
async def technical(symbol: SymbolPath, _user: UserDep, services: ServicesDep) -> TechnicalReport:
    return await services.analysis.technical(symbol)


@router.get("/{symbol}/macro", dependencies=[Depends(limited(MACRO))])
async def macro(symbol: SymbolPath, user: UserDep, services: ServicesDep) -> MacroResponse:
    return await services.analysis.macro(symbol, user.id)


@router.get("/{symbol}/news", dependencies=[Depends(limited(STOCK))])
async def news(symbol: SymbolPath, user: UserDep, services: ServicesDep) -> NewsProgressOut:
    """Starts news collection when needed (within the daily budget) and reports its progress."""
    return await services.analysis.news_progress(symbol, user.id)
