"""Market data use-cases: quotes, search, price bars and corporate events, cache-first.

The provider is already guarded (see ``ProviderGuard.wrap_market``). A provider failure never
becomes a 500: the service falls back to whatever is saved and says so in a ``DataStatus``. The
only hard failures are an unknown symbol (404) and "nothing saved and the provider is down" for
prices (503).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import BaseModel

from app.db import Database
from app.logging_setup import get_logger
from app.providers.base import MarketDataProvider
from app.providers.errors import ProviderError, SymbolNotFoundError
from app.providers.models import Bar, CorporateEvent, Interval, Quote, SymbolMatch
from app.repositories.bars import BarsRepository, FetchState
from app.repositories.cache import CacheRepository
from app.repositories.events import EventsFetchState, EventsRepository
from app.services.calendars import (
    exchange_tz,
    is_session_open,
    last_completed_session,
    root_ticker,
    session_close,
)
from app.services.errors import AppError
from app.services.status import DataStatus, describe_failure, ok, stale_status

log = get_logger(__name__)

DAILY_HISTORY_DAYS = 1100  # 3 years plus slack: covers 2 years of sessions + 200 warm-up sessions
HOURLY_HISTORY_DAYS = 60  # enough for the 1M chart (22 sessions) plus indicator warm-up
EVENTS_START_DAYS = 760  # one shared start so the events cache is reused across endpoints
REFRESH_AFTER = timedelta(minutes=15)
EVENTS_REFRESH_AFTER = timedelta(hours=24)
QUOTE_TTL = timedelta(seconds=60)
SEARCH_TTL = timedelta(hours=1)
# Callers ask for a start date relative to "today", so the requested start creeps forward by a
# day each day. Without slack the stored coverage would look insufficient every morning.
COVERAGE_SLACK = timedelta(days=7)
_COLUMNS = ["open", "high", "low", "close", "volume"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def bars_to_frame(bars: list[Bar], interval: Interval, tz: ZoneInfo) -> pd.DataFrame:
    """Domain-convention frame: naive index (session date, or exchange-local time) + float OHLCV."""
    if interval == "1d":
        index = pd.DatetimeIndex([pd.Timestamp(b.ts.date()) for b in bars])
    else:
        index = pd.DatetimeIndex(
            [pd.Timestamp(b.ts.astimezone(tz).replace(tzinfo=None)) for b in bars]
        )
    frame = pd.DataFrame(
        [(b.open, b.high, b.low, b.close, b.volume) for b in bars],
        index=index,
        columns=pd.Index(_COLUMNS),
        dtype=float,
    )
    # The domain functions reject NaN prices, so incomplete rows are dropped here.
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def _unavailable(what: str, symbol: str, exc: ProviderError) -> AppError:
    return AppError(
        503,
        "data_unavailable",
        f"{what} for {symbol} is temporarily unavailable ({describe_failure(exc)}) and nothing "
        "has been saved yet. "
        "Please try again in a few minutes.",
    )


def _not_found(symbol: str) -> AppError:
    return AppError(404, "not_found", f"We could not find a stock with the symbol {symbol}.")


class _HasFetchTime(Protocol):
    @property
    def last_fetched_at(self) -> datetime: ...


@dataclass(frozen=True)
class _CacheKind:
    """How one kind of cached payload is described to the user."""

    ttl: timedelta
    what: str  # "price quote", as in "The price quote for X is unavailable"
    noun: str  # "quote", as in "Showing the last saved quote"


class _Matches(BaseModel):
    """The cached shape of a search result (the cache stores JSON objects, not bare lists)."""

    matches: list[SymbolMatch]


_QUOTE = _CacheKind(QUOTE_TTL, "price quote", "quote")
_SEARCH = _CacheKind(SEARCH_TTL, "stock search", "search results")


def _status(
    label: str, noun: str, state: _HasFetchTime, now: datetime, failure: ProviderError | None
) -> DataStatus:
    """ "ok" as of the last fetch, or "stale" when the refresh just failed."""
    if failure is None:
        return ok(state.last_fetched_at)
    return stale_status(label, noun, state.last_fetched_at, now, failure)


class MarketDataService:
    def __init__(
        self,
        db: Database,
        provider: MarketDataProvider,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._bars = BarsRepository(db)
        self._events = EventsRepository(db)
        self._cache = CacheRepository(db)
        self._provider = provider
        self._clock = clock

    # --- quote and search ------------------------------------------------------------------

    async def quote(self, symbol: str) -> tuple[Quote, DataStatus]:
        quote, degraded = await self._cached(
            _QUOTE, f"quote:{symbol}", symbol, Quote, lambda: self._provider.quote(symbol)
        )
        return quote, degraded or ok(quote.as_of)

    async def search(self, query: str) -> list[SymbolMatch]:
        """Matches for ``query``; a stale fallback is logged (the endpoint returns a bare list)."""
        text = query.strip()
        if not text:
            return []

        async def fetch() -> _Matches:
            return _Matches(matches=await self._provider.search(text))

        found, _ = await self._cached(_SEARCH, f"search:{text.lower()}", text, _Matches, fetch)
        return found.matches

    async def _cached[M: BaseModel](
        self,
        kind: _CacheKind,
        key: str,
        subject: str,
        model: type[M],
        fetch: Callable[[], Awaitable[M]],
    ) -> tuple[M, DataStatus | None]:
        """Cache-first read; the status is None for fresh data and says what is wrong otherwise.

        An unknown symbol is a 404. When the provider fails, a saved copy (however old) is served
        as "stale", and only with no copy at all does the failure become a 503.
        """
        now = self._clock()
        entry = await self._cache.lookup(key)
        if entry is not None and entry.is_fresh(now):
            return model.model_validate(entry.payload), None
        try:
            value = await fetch()
        except SymbolNotFoundError as exc:
            raise _not_found(subject) from exc
        except ProviderError as exc:
            if entry is None:
                raise _unavailable(f"The {kind.what}", subject, exc) from exc
            log.warning("cache_stale_fallback", key=key, error=str(exc))
            status = stale_status(kind.what.capitalize(), kind.noun, entry.created_at, now, exc)
            return model.model_validate(entry.payload), status
        await self._cache.put(key, value.model_dump(mode="json"), kind.ttl, now)
        return value, None

    # --- bars ------------------------------------------------------------------------------

    async def daily_bars(
        self, symbol: str, start: date, end: date
    ) -> tuple[pd.DataFrame, DataStatus]:
        """Completed daily bars for sessions in [start, end]; today's bar is dropped while open."""
        begin = datetime(start.year, start.month, start.day, tzinfo=UTC)
        bars, status = await self._load(symbol, "1d", begin)
        wanted = [b for b in bars if start <= b.ts.date() <= end]
        return bars_to_frame(wanted, "1d", exchange_tz(symbol)), status

    async def hourly_bars(
        self, symbol: str, start: datetime, end: datetime
    ) -> tuple[pd.DataFrame, DataStatus]:
        """Completed hourly bars in [start, end] as exchange-local naive timestamps."""
        bars, status = await self._load(symbol, "1h", start)
        wanted = [b for b in bars if start <= b.ts <= end]
        return bars_to_frame(wanted, "1h", exchange_tz(symbol)), status

    async def daily_history(self, symbol: str) -> tuple[pd.DataFrame, DataStatus]:
        """The standard ~3 year daily history every analysis shares (one cache, one fetch)."""
        today = self._clock().astimezone(UTC).date()
        return await self.daily_bars(symbol, today - timedelta(days=DAILY_HISTORY_DAYS), today)

    async def hourly_history(self, symbol: str) -> tuple[pd.DataFrame, DataStatus]:
        now = self._clock()
        return await self.hourly_bars(symbol, now - timedelta(days=HOURLY_HISTORY_DAYS), now)

    async def _load(
        self, symbol: str, interval: Interval, start: datetime
    ) -> tuple[list[Bar], DataStatus]:
        now = self._clock()
        end = now + timedelta(days=1)

        async def fetch() -> FetchState:
            try:
                fetched = await self._provider.bars(symbol, interval, start, end)
            except SymbolNotFoundError as exc:
                raise _not_found(symbol) from exc
            return await self._bars.replace_range(
                symbol, interval, fetched, start=start, end=end, fetched_at=now
            )

        state = await self._bars.get_state(symbol, interval)
        refresh = self._needs_refresh(symbol, interval, state, start, now)
        try:
            state, failure = await self._refresh(f"bars {interval}", symbol, state, refresh, fetch)
        except ProviderError as exc:
            raise _unavailable("Price data", symbol, exc) from exc
        stored = await self._bars.get_range(symbol, interval, start, end)
        bars = self._completed(symbol, interval, stored, now)
        if not bars:
            if failure is not None:
                raise _unavailable("Price data", symbol, failure)
            raise _not_found(symbol)
        return bars, _status("Price data", "prices", state, now, failure)

    def _needs_refresh(
        self,
        symbol: str,
        interval: Interval,
        state: FetchState | None,
        start: datetime,
        now: datetime,
    ) -> bool:
        if state is None or state.covered_start > start + COVERAGE_SLACK:
            return True
        last_done = last_completed_session(symbol, now)
        close = session_close(symbol, last_done)
        if close is not None and state.last_fetched_at < close:
            return True  # fetched before the last session finished, so its final bar is missing
        if now - state.last_fetched_at < REFRESH_AFTER:
            return False  # also stops us hammering the vendor when it lags behind
        if state.last_bar_at is None or state.last_bar_at.date() < last_done:
            return True
        # Daily bars never include the in-progress session, so only hourly data goes stale
        # while the market is open.
        return interval == "1h" and is_session_open(symbol, now)

    @staticmethod
    def _completed(symbol: str, interval: Interval, bars: list[Bar], now: datetime) -> list[Bar]:
        """Drop the bar still being formed: today's daily bar, or the current hour."""
        last_done = last_completed_session(symbol, now)
        if interval == "1d":
            return [b for b in bars if b.ts.date() <= last_done]
        tz = exchange_tz(symbol)
        return [
            b
            for b in bars
            if b.ts + timedelta(hours=1) <= now or b.ts.astimezone(tz).date() <= last_done
        ]

    # --- corporate events ------------------------------------------------------------------

    async def standard_events(self, symbol: str) -> tuple[list[CorporateEvent], DataStatus]:
        """Events over the shared window every analysis uses (one cache, one fetch)."""
        today = self._clock().astimezone(UTC).date()
        return await self.events(symbol, today - timedelta(days=EVENTS_START_DAYS), today)

    async def company_name(self, symbol: str) -> str:
        """The quote's name, or the bare ticker when no quote can be had."""
        try:
            quote, _ = await self.quote(symbol)
        except AppError:
            return root_ticker(symbol)
        return quote.name

    async def events(
        self, symbol: str, start: date, end: date
    ) -> tuple[list[CorporateEvent], DataStatus]:
        """Events dated in [start, end]. Never raises for provider trouble: events are optional."""
        now = self._clock()

        async def fetch() -> EventsFetchState:
            begin = datetime(start.year, start.month, start.day, tzinfo=UTC)
            until = datetime(end.year, end.month, end.day, tzinfo=UTC)
            fetched = await self._provider.events(symbol, begin, until)
            return await self._events.upsert_many(
                symbol, fetched, start=start, end=end, fetched_at=now
            )

        state = await self._events.get_state(symbol)
        stale = (
            state is None
            or now - state.last_fetched_at > EVENTS_REFRESH_AFTER
            or state.covered_start > start + COVERAGE_SLACK
        )
        try:
            state, failure = await self._refresh("events", symbol, state, stale, fetch)
        except ProviderError as exc:
            reason = (
                f"Corporate events are unavailable: {describe_failure(exc)}. "
                "Earnings, dividend and split markers are hidden for now."
            )
            return [], DataStatus(state="unavailable", as_of=None, reason=reason)
        events = await self._events.get_range(symbol, start, end)
        return events, _status("Corporate event data", "events", state, now, failure)

    @staticmethod
    async def _refresh[S: _HasFetchTime](
        dataset: str,
        symbol: str,
        state: S | None,
        needed: bool,
        fetch: Callable[[], Awaitable[S]],
    ) -> tuple[S, ProviderError | None]:
        """Run ``fetch`` (it saves the data and returns the new fetch state) when ``needed``.

        Returns the state to report and the failure that was absorbed, if any: when the provider
        fails but something is saved, that is the old state. With nothing saved the failure is
        raised, since there is nothing to fall back on.
        """
        if state is not None and not needed:
            return state, None
        try:
            return await fetch(), None
        except ProviderError as exc:
            log.warning("provider_fetch_failed", dataset=dataset, symbol=symbol, error=str(exc))
            if state is None:
                raise
            return state, exc
