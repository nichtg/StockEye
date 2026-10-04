"""Analysis use-cases: technical outlook, macro (news-sentiment) report, and chart data.

All statistics live in ``app.domain`` (assembled in ``compute``); this module fetches inputs
(cache-first, in parallel), runs the pure code off the event loop, and attaches a ``DataStatus``
to every result.
"""

import asyncio
import dataclasses
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from bson import ObjectId
from pydantic import BaseModel

from app.clock import utc_now
from app.db import Database
from app.domain.macro import ScoredArticle
from app.logging_setup import get_logger
from app.repositories.cache import CacheRepository
from app.services import compute
from app.services.admission import NewSymbolAdmission
from app.services.calendars import session_calendar, spec_for
from app.services.charts import INDICATORS, RANGES
from app.services.errors import AppError
from app.services.market_data import MarketDataService
from app.services.news import IngestProgress, NewsService
from app.services.reports import (
    ChartData,
    FullStatuses,
    IngestionOut,
    MacroReportOut,
    MacroResponse,
    NewsProgressOut,
    PriceStatuses,
    RangeKey,
    TechnicalReport,
)
from app.services.status import DataStatus, combine

log = get_logger(__name__)

TECHNICAL_TTL = timedelta(minutes=15)
MACRO_TTL = timedelta(hours=1)
MARKERS_TTL = timedelta(minutes=5)
NEWS_WINDOW_DAYS = 730  # two years of news
MIN_HISTORY_BARS = 30
NEW_SYMBOL_LIMIT_REASON = "Daily limit for analysing new stocks reached; try again tomorrow."
# Bump when a cached report's shape changes, so a deploy never serves the old shape.
CACHE_SCHEMA = 2
# Macro reports have their own version: 3 = estimation window [t-250, t-20] with only earnings
# masked, plus the ``events`` list. Reports cached under the old method must never be served.
MACRO_CACHE_SCHEMA = 3


type _NewsInputs = tuple[IngestProgress, list[ScoredArticle], DataStatus]


class _MarkerEntry(BaseModel):
    date: date
    label: str
    car_0_1: float


class _MarkerCache(BaseModel):
    """Chart news markers only; never a macro report, so it may hold a partial build."""

    markers: list[_MarkerEntry]


def markers_cache_key(symbol: str, progress: IngestProgress) -> str:
    """Changes whenever stored news changes (a month finishes or a top-up lands)."""
    stamp = progress.updated_at.isoformat() if progress.updated_at is not None else "never"
    return f"markers:v{MACRO_CACHE_SCHEMA}:{symbol}:{progress.months_done}:{stamp}"


def macro_cache_key(symbol: str) -> str:
    return f"macro:v{MACRO_CACHE_SCHEMA}:{symbol}"


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


def _news_markers(cached: MacroResponse | None) -> list[tuple[date, str, float]]:
    """Every evaluated event of a macro report (cached or built from stored news) as a marker."""
    report = cached.report if cached is not None else None
    if report is None:
        return []
    return [(e.date, e.headline or "News event", e.car_0_1) for e in report.events]


class AnalysisService:
    def __init__(
        self,
        db: Database,
        market: MarketDataService,
        news: NewsService,
        admission: NewSymbolAdmission,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._cache = CacheRepository(db)
        self._admission = admission
        self._market = market
        self._news = news
        self._clock = clock

    # --- technical -------------------------------------------------------------------------

    async def _fresh[M: BaseModel](self, key: str, now: datetime, model: type[M]) -> M | None:
        """The cached report if it has not expired and still fits ``model`` (else a miss)."""
        entry = await self._cache.lookup(key)
        return entry.parse(model) if entry is not None and entry.is_fresh(now) else None

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
        key = f"technical:v{CACHE_SCHEMA}:{symbol}:{frame.index[-1].date().isoformat()}"
        if (cached := await self._fresh(key, now, TechnicalReport)) is not None:
            return cached.model_copy(update={"data_status": statuses})
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
        has analysed yet needs admission (``user_id``'s daily budget); past it the report is built
        without news and says why.
        """
        now = self._clock()
        if (cached := await self._fresh(macro_cache_key(symbol), now, MacroResponse)) is not None:
            return cached
        return await self._build_macro(
            symbol, now, lambda name: self._news_inputs(symbol, name, user_id, now)
        )

    async def news_progress(self, symbol: str, user_id: ObjectId) -> NewsProgressOut:
        """Start news collection if needed and report progress; cheap enough to poll.

        Shares the admission-then-ensure path with ``macro``. An unknown symbol raises 404; a
        refused symbol starts nothing and reports the refusal as its status.
        """
        # Validate first (404 for an unknown symbol), so junk symbols never reach admission.
        quote, _ = await self._market.quote(symbol)
        progress, refused = await self._start_news(symbol, quote.name, user_id)
        status = refused if refused is not None else await self._news.status(symbol)
        return NewsProgressOut(**dataclasses.asdict(progress), status=status)

    async def _build_macro(
        self,
        symbol: str,
        now: datetime,
        news_inputs: Callable[[str], Awaitable[_NewsInputs]],
    ) -> MacroResponse:
        """Build the macro response from prices plus whatever news ``news_inputs`` yields.

        Caches it only when complete and fully ok, so a half-built report is never served for an
        hour. ``news_inputs`` receives the company name and decides whether collection may start.
        """
        today = now.astimezone(UTC).date()
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
        progress, articles, news_status = await news_inputs(name)
        report: MacroReportOut | None = None
        if bench is not None:
            cal = session_calendar(
                symbol, (now - timedelta(days=NEWS_WINDOW_DAYS)).date(), today + timedelta(days=14)
            )
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
        if complete:
            await self._cache.put(
                macro_cache_key(symbol), response.model_dump(mode="json"), MACRO_TTL, now
            )
        return response

    async def _start_news(
        self, symbol: str, name: str, user_id: ObjectId
    ) -> tuple[IngestProgress, DataStatus | None]:
        """Admission, then ensure ingestion. A refused symbol gets (progress, refusal status)."""
        if not await self._admission.admit(user_id, symbol):
            refused = DataStatus(state="unavailable", reason=NEW_SYMBOL_LIMIT_REASON)
            return await self._news.progress(symbol), refused
        return await self._news.ensure_ingested(symbol, name), None

    async def _news_inputs(
        self, symbol: str, name: str, user_id: ObjectId, now: datetime
    ) -> _NewsInputs:
        """Ingestion progress, scored articles and news status; no news for a refused symbol."""
        progress, refused = await self._start_news(symbol, name, user_id)
        if refused is not None:
            return progress, [], refused
        return progress, *await self._news.scored_articles(
            symbol, now - timedelta(days=NEWS_WINDOW_DAYS), now
        )

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

    async def _marker_inputs(self, symbol: str, now: datetime) -> list[tuple[date, str, float]]:
        """News markers for the chart from stored news only; never starts collection.

        Uses the fresh cached macro report when there is one. Otherwise it builds from stored
        articles, but only when some exist, and caches just the marker list for a few minutes
        (keyed by what is stored), so chart loads never recompute on every request. A failure
        only costs the news markers, never the chart.
        """
        try:
            return await self._markers(symbol, now)
        except Exception:
            log.warning("chart_news_markers_failed", symbol=symbol, exc_info=True)
            return []

    async def _markers(self, symbol: str, now: datetime) -> list[tuple[date, str, float]]:
        if (cached := await self._fresh(macro_cache_key(symbol), now, MacroResponse)) is not None:
            return _news_markers(cached)
        progress = await self._news.progress(symbol)
        if progress.months_done == 0:
            return []
        key = markers_cache_key(symbol, progress)
        if (hit := await self._fresh(key, now, _MarkerCache)) is not None:
            return [(m.date, m.label, m.car_0_1) for m in hit.markers]
        articles, status = await self._news.scored_articles(
            symbol, now - timedelta(days=NEWS_WINDOW_DAYS), now
        )
        if not articles:
            return []

        async def stored(_name: str) -> _NewsInputs:
            return progress, articles, status

        markers = _news_markers(await self._build_macro(symbol, now, stored))
        entry = _MarkerCache(
            markers=[_MarkerEntry(date=d, label=h, car_0_1=c) for d, h, c in markers]
        )
        await self._cache.put(key, entry.model_dump(mode="json"), MARKERS_TTL, now)
        return markers

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
            news_markers,
        ) = await asyncio.gather(
            prices,
            self._market.standard_events(symbol),
            self._news.status(symbol),
            self._marker_inputs(symbol, now),
        )
        try:
            return await asyncio.to_thread(
                compute.build_chart,
                symbol,
                range_key,
                indicators,
                frame=frame,
                events=events,
                news=news_markers,
                statuses=_full_statuses(price_status, event_status, news_status),
            )
        except ValueError as exc:
            raise _bad_data(symbol) from exc
