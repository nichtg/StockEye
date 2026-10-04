"""The two seams between StockEye and the outside world.

``MarketDataProvider`` has two adapters (Yahoo in production, an in-memory fake in tests);
``NewsProvider`` has several (Google News RSS, Finnhub, Marketaux, Alpha Vantage, plus test fakes).
Adapters raise only the errors in ``app.providers.errors``.
"""

from datetime import datetime
from typing import Protocol

from app.providers.models import (
    Bar,
    CorporateEvent,
    Exchange,
    Interval,
    NewsItem,
    NewsQuery,
    Quote,
    SymbolMatch,
)


class MarketDataProvider(Protocol):
    name: str

    async def search(self, query: str) -> list[SymbolMatch]: ...

    async def quote(self, symbol: str) -> Quote: ...

    async def bars(
        self, symbol: str, interval: Interval, start: datetime, end: datetime
    ) -> list[Bar]: ...

    async def events(self, symbol: str, start: datetime, end: datetime) -> list[CorporateEvent]: ...


class NewsProvider(Protocol):
    name: str
    # Declared, not checked inside ``fetch``, so callers can skip an adapter that cannot answer
    # (and spend none of its quota) before calling it.
    exchanges: frozenset[Exchange]

    async def fetch(self, query: NewsQuery) -> list[NewsItem]: ...
