"""The one gate for symbols the app has never ingested news for."""

from collections.abc import Callable
from datetime import datetime

from bson import ObjectId

from app.repositories.ingest_budget import IngestBudget
from app.services.news import NewsService


class NewSymbolAdmission:
    """Decides which symbols may have their news backfilled.

    A symbol qualifies if it already has news history, was admitted before, or ``user_id`` can
    spend one of today's admissions on it. Every entry point (the macro report, adding to a
    watchlist) goes through ``admit``; the scheduled job only asks ``is_admitted``.
    """

    def __init__(
        self, budget: IngestBudget, news: NewsService, clock: Callable[[], datetime]
    ) -> None:
        self._budget = budget
        self._news = news
        self._clock = clock

    async def is_admitted(self, symbol: str) -> bool:
        return await self._news.has_history(symbol) or await self._budget.is_admitted(symbol)

    async def admit(self, user_id: ObjectId, symbol: str) -> bool:
        return await self._news.has_history(symbol) or await self._budget.admit(
            user_id, symbol, self._clock()
        )
