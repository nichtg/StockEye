"""Analysis use-cases: technical outlook, macro (news-sentiment) report, and chart data.

All statistics live in ``app.domain`` (assembled in ``compute``); this module fetches inputs
(cache-first, in parallel), runs the pure code off the event loop, and attaches a ``DataStatus``
to every result.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
from bson import ObjectId

from app.db import Database
from app.repositories.cache import CacheRepository
from app.repositories.ingest_budget import IngestBudget
from app.services import compute
from app.services.calendars import session_calendar, spec_for
from app.services.charts import INDICATORS, RANGES
from app.services.errors import AppError
from app.services.market_data import MarketDataService
from app.services.news import NewsService
from app.services.reports import (
    ChartData,
    FullStatuses,
    IngestionOut,
    MacroReportOut,
    MacroResponse,
    PriceStatuses,
    RangeKey,
    TechnicalReport,
)
from app.services.status import DataStatus, combine

TECHNICAL_TTL = timedelta(minutes=15)
MACRO_TTL = timedelta(hours=1)
NEWS_WINDOW_DAYS = 730  # two years of news
MIN_HISTORY_BARS = 30
NEW_SYMBOL_LIMIT_REASON = "Daily limit for analysing new stocks reached; try again tomorrow."


def _utc_now() -> datetime:
    return datetime.now(UTC)


def macro_cache_key(symbol: str) -> str:
    return f"macro:{symbol}"


def _bad_data(symbol: str) -> AppError:
    return AppError(
        503,
        "data_unavailable",
        f"The saved price history for {symbol} looks damaged, so it cannot be analysed yet. "
        "Please try again later.",
    )


def _full_statuses(prices: DataStatus, events: DataStatus, news: DataStatus) -> FullStatuses:
    return FullStatuses(
        prices=prices, events=events, news=news, overall=combine([prices, events, news])
    )


def _news_markers(payload: dict[str, Any] | None) -> list[tuple[date, str, float]]:
    """High-impact days from a cached macro report; never triggers a computation."""
    if payload is None:
        return []
    report = MacroResponse.model_validate(payload).report
    if report is None:
        return []
    return [
        (e.date, e.headlines[0].title if e.headlines else "High-impact news", e.car_0_1)
        for e in report.top_events
    ]


class AnalysisService:
    def __init__(
        self,
        db: Database,
        market: MarketDataService,
        news: NewsService,
        clock: Callable[[], datetime] = _utc_now,
        *,
        max_new_symbols_per_user_per_day: int,
    ) -> None:
        self._cache = CacheRepository(db)
        self._budget = IngestBudget(db, max_new_symbols_per_user_per_day)
        self._market = market
        self._news = news
        self._clock = clock

    # --- technical -------------------------------------------------------------------------

    async def _fresh(self, key: str, now: datetime) -> dict[str, Any] | None:
        """The cached payload if it has not expired."""
        entry = await self._cache.lookup(key)
        return entry.payload if entry is not None and entry.is_fresh(now) else None

    async def technical(self, symbol: str) -> TechnicalReport:
        """1-week outlook from daily bars; cached 15 minutes per symbol and last bar date."""
        now = self._clock()
        frame, status = await self._market.daily_history(symbol)
        if len(frame) < MIN_HISTORY_BARS:
            raise AppError(
                422,
                "insufficient_history",
                f"{symbol} has too little price history for a technical outlook yet.",
            )
        statuses = PriceStatuses(prices=status, overall=combine([status]))
        key = f"technical:{symbol}:{frame.index[-1].date().isoformat()}"
        if (cached := await self._fresh(key, now)) is not None:
            report = TechnicalReport.model_validate(cached)
            return report.model_copy(update={"data_status": statuses})
        try:
            report = await asyncio.to_thread(compute.compute_technical, symbol, frame, statuses)
        except ValueError as exc:
            raise _bad_data(symbol) from exc
        if status.state == "ok":  # never freeze a degraded answer for 15 minutes
            await self._cache.put(key, report.model_dump(mode="json"), TECHNICAL_TTL, now)
        return report

    # --- macro -----------------------------------------------------------------------------

    async def macro(self, symbol: str, user_id: ObjectId) -> MacroResponse:
        """News-sentiment event study. Starts background news ingestion when needed.

        Returns whatever can be computed now plus ingestion progress, so the UI can poll. Only a
        complete, fully healthy result is cached (1 hour). Starting ingestion for a symbol nobody
        has analysed yet counts against ``user_id``'s daily budget; past it the report is built
        without news and says why.
        """
        now = self._clock()
        key = macro_cache_key(symbol)
        if (cached := await self._fresh(key, now)) is not None:
            return MacroResponse.model_validate(cached)
        today = now.astimezone(UTC).date()
        news_start = now - timedelta(days=NEWS_WINDOW_DAYS)
        (
            (stock, price_status),
            name,
            (bench, bench_status),
            (events, event_status),
        ) = await asyncio.gather(
            self._market.daily_history(symbol),
            self._market.company_name(symbol),
            self._benchmark(symbol),
            self._market.standard_events(symbol),
        )
        admitted = await self._news.has_history(symbol) or await self._budget.try_spend(
            user_id, symbol, now
        )
        if admitted:
            progress = await self._news.ensure_ingested(symbol, name)
        else:
            progress = await self._news.progress(symbol)
        articles, news_status = await self._news.scored_articles(symbol, news_start, now)
        if not admitted:
            news_status = DataStatus(state="unavailable", reason=NEW_SYMBOL_LIMIT_REASON)
        report: MacroReportOut | None = None
        if bench is not None:
            cal = session_calendar(symbol, news_start.date(), today + timedelta(days=14))
            earnings = [e.date for e in events if e.kind == "earnings"]
            report = await asyncio.to_thread(
                compute.compute_macro, stock, bench, articles, earnings, cal
            )
        statuses = _full_statuses(combine([price_status, bench_status]), event_status, news_status)
        ingestion = IngestionOut.model_validate(progress, from_attributes=True)
        response = MacroResponse(
            symbol=symbol, name=name, report=report, ingestion=ingestion, data_status=statuses
        )
        complete = (
            not ingestion.in_progress
            and ingestion.months_done == ingestion.months_total
            and statuses.overall.state == "ok"
        )
        if complete:  # a half-built report must not be served for an hour
            await self._cache.put(key, response.model_dump(mode="json"), MACRO_TTL, now)
        return response

    async def _benchmark(self, symbol: str) -> tuple[pd.DataFrame | None, DataStatus]:
        """Daily closes of the first benchmark with data; (None, partial) if none responds."""
        for bench in spec_for(symbol).benchmarks:
            try:
                return await self._market.daily_history(bench)
            except AppError:
                continue
        reason = "Market benchmark prices are unavailable, so the news study could not be run."
        return None, DataStatus(state="partial", as_of=None, reason=reason)

    # --- chart -----------------------------------------------------------------------------

    async def chart(self, symbol: str, range_key: RangeKey, indicators: list[str]) -> ChartData:
        """Candles, requested indicator lines and markers for ``range_key``."""
        unknown = [i for i in indicators if i not in INDICATORS]
        if unknown:
            raise AppError(
                422,
                "validation_error",
                f"Unknown indicator: {unknown[0]}. Choose from {', '.join(INDICATORS)}.",
            )
        now = self._clock()
        interval, _ = RANGES[range_key]
        prices = (
            self._market.hourly_history(symbol)
            if interval == "1h"
            else self._market.daily_history(symbol)
        )
        (
            (frame, price_status),
            (events, event_status),
            news_status,
            macro_payload,
        ) = await asyncio.gather(
            prices,
            self._market.standard_events(symbol),
            self._news.status(symbol),
            self._fresh(macro_cache_key(symbol), now),
        )
        try:
            return await asyncio.to_thread(
                compute.build_chart,
                symbol,
                range_key,
                indicators,
                frame=frame,
                events=events,
                news=_news_markers(macro_payload),
                statuses=_full_statuses(price_status, event_status, news_status),
            )
        except ValueError as exc:
            raise _bad_data(symbol) from exc
