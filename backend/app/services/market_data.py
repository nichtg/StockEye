"""Market data use-cases: quotes, search, price bars and corporate events, cache-first.

The provider is already guarded (see ``ProviderGuard.wrap_market``). A provider failure never
becomes a 500: the service falls back to whatever is saved and says so in a ``DataStatus``. The
only hard failures are an unknown symbol (404) and "nothing saved and the provider is down" for
prices (503).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import BaseModel, ValidationError

from app.clock import utc_now
from app.db import Database
from app.logging_setup import get_logger
from app.providers.base import MarketDataProvider
from app.providers.errors import ProviderDataError, ProviderError, SymbolNotFoundError
from app.providers.models import Bar, CorporateEvent, Interval, Quote, SymbolMatch
from app.repositories.bars import BarsRepository, FetchState
from app.repositories.cache import CacheEntry, CacheRepository
from app.repositories.events import EventsFetchState, EventsRepository
from app.services.bar_policy import COVERAGE_SLACK, completed, needs_refresh, window_start
from app.services.calendars import (
    exchange_tz,
    root_ticker,
)
from app.services.errors import AppError
from app.services.singleflight import SingleFlight
from app.services.status import DataStatus, describe_failure, ok, stale_status

log = get_logger(__name__)

EVENTS_START_DAYS = 760  # one shared start so the events cache is reused across endpoints
EVENTS_REFRESH_AFTER = timedelta(hours=24)
QUOTE_TTL = timedelta(seconds=60)
UNKNOWN_SYMBOL_TTL = timedelta(hours=6)  # how long "no such stock" is remembered
SEARCH_TTL = timedelta(hours=1)
_COLUMNS = ["open", "high", "low", "close", "volume"]


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


def _not_found() -> AppError:
    return AppError(404, "not_found", "We couldn't find that stock.")


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


# A cache entry holds {"found": payload} or _NOT_FOUND, so "no such stock" is never mistaken for
# a payload of the wrong shape.
_NOT_FOUND: dict[str, Any] = {"not_found": True}

_QUOTE = _CacheKind(QUOTE_TTL, "price quote", "quote")
_SEARCH = _CacheKind(SEARCH_TTL, "stock search", "search results")


def _saved[M: BaseModel](entry: CacheEntry | None, model: type[M]) -> M | None:
    """The saved payload as ``model``; None if absent or in a shape an old build wrote."""
    try:
        return None if entry is None else model.model_validate(entry.payload["found"])
    except (KeyError, ValidationError):
        return None


def _fresh_hit[M: BaseModel](entry: CacheEntry | None, now: datetime, model: type[M]) -> M | None:
    """The saved value if usable now; raises the 404 if a fresh entry says the symbol is unknown."""
    if entry is None or not entry.is_fresh(now):
        return None
    if entry.payload == _NOT_FOUND:
        raise _not_found()
    return _saved(entry, model)


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
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._bars = BarsRepository(db)
        self._events = EventsRepository(db)
        self._cache = CacheRepository(db)
        self._provider = provider
        self._clock = clock
        # Cold requests fan out (quote, chart, outlook, overview all want the same bars at once);
        # one fetch per series serves them all instead of racing to write duplicate rows.
        self._bar_flights = SingleFlight[tuple[FetchState, ProviderError | None]]()
        self._cache_flights = SingleFlight[Any]()
        self._event_flights = SingleFlight[tuple[EventsFetchState, ProviderError | None]]()

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

        An unknown symbol is a 404, remembered for ``UNKNOWN_SYMBOL_TTL`` so repeated lookups of a
        made-up symbol cost no vendor calls. When the provider fails, a saved copy (however old)
        is served as "stale", and only with no copy at all does the failure become a 503. A saved
        copy that no longer fits ``model`` (written by an older build) counts as no copy.
        """
        now = self._clock()
        entry = await self._cache.lookup(key)
        if (hit := _fresh_hit(entry, now, model)) is not None:
            return hit, None
        try:
            value = await self._cache_flights.run(
                key, lambda: self._fetch_and_store(kind, key, model, fetch)
            )
        except ProviderError as exc:
            saved = _saved(entry, model)  # an expired "unknown" is no fallback
            if entry is None or saved is None:
                raise _unavailable(f"The {kind.what}", subject, exc) from exc
            log.warning("cache_stale_fallback", key=key, error=str(exc))
            status = stale_status(kind.what.capitalize(), kind.noun, entry.created_at, now, exc)
            return saved, status
        return value, None

    async def _fetch_and_store[M: BaseModel](
        self,
        kind: _CacheKind,
        key: str,
        model: type[M],
        fetch: Callable[[], Awaitable[M]],
    ) -> M:
        """The body of one single flight per cache key: fetch and save (unless just saved)."""
        now = self._clock()
        # a concurrent flight may have finished since the caller looked
        if (hit := _fresh_hit(await self._cache.lookup(key), now, model)) is not None:
            return hit
        try:
            value = await fetch()
        except SymbolNotFoundError as exc:
            await self._cache.put(key, _NOT_FOUND, UNKNOWN_SYMBOL_TTL, now)
            raise _not_found() from exc
        await self._cache.put(key, {"found": value.model_dump(mode="json")}, kind.ttl, now)
        return value

    # --- bars ------------------------------------------------------------------------------

    async def daily_history(self, symbol: str) -> tuple[pd.DataFrame, DataStatus]:
        """The standard ~3 year daily history every analysis shares (one cache, one fetch)."""
        return await self._history(symbol, "1d")

    async def hourly_history(self, symbol: str) -> tuple[pd.DataFrame, DataStatus]:
        """The standard hourly history, as exchange-local naive timestamps."""
        return await self._history(symbol, "1h")

    async def _history(self, symbol: str, interval: Interval) -> tuple[pd.DataFrame, DataStatus]:
        bars, status = await self._load(symbol, interval)
        return bars_to_frame(bars, interval, exchange_tz(symbol)), status

    async def _load(self, symbol: str, interval: Interval) -> tuple[list[Bar], DataStatus]:
        now = self._clock()
        start = window_start(interval, now)
        end = now + timedelta(days=1)
        try:
            state, failure = await self._bar_flights.run(
                (symbol, interval), lambda: self._refresh_bars(symbol, interval)
            )
        except ProviderError as exc:
            raise _unavailable("Price data", symbol, exc) from exc
        stored = await self._bars.get_range(symbol, interval, start, end)
        bars = completed(symbol, interval, stored, now)
        if not bars:
            if failure is not None:
                raise _unavailable("Price data", symbol, failure)
            raise _not_found()
        return bars, _status("Price data", "prices", state, now, failure)

    async def _refresh_bars(
        self, symbol: str, interval: Interval
    ) -> tuple[FetchState, ProviderError | None]:
        """Bring the saved bars up to date if they need it (the body of one single flight).

        The window is fixed per interval and computed here, so every caller of one series asks
        the vendor for the same range. Deciding and fetching both happen inside the flight, so
        no caller can decide on a state that a concurrent fetch is about to replace.
        """
        now = self._clock()
        start = window_start(interval, now)
        end = now + timedelta(days=1)
        state = await self._bars.get_state(symbol, interval)

        async def fetch() -> FetchState:
            try:
                fetched = await self._provider.bars(symbol, interval, start, end)
            except SymbolNotFoundError as exc:
                raise _not_found() from exc
            if not fetched and state is not None:
                # Saved history exists, so "nothing came back" is a vendor glitch, not a verdict:
                # saving it would erase the range.
                raise ProviderDataError(self._provider.name, "empty bars")
            return await self._bars.replace_range(
                symbol, interval, fetched, start=start, end=end, fetched_at=now
            )

        refresh = needs_refresh(symbol, interval, state, start, now)
        return await self._refresh(f"bars {interval}", symbol, state, refresh, fetch)

    # --- corporate events ------------------------------------------------------------------

    async def standard_events(self, symbol: str) -> tuple[list[CorporateEvent], DataStatus]:
        """Events over the one window every analysis shares (one cache, one fetch).

        Never raises for provider trouble: events are optional.
        """
        now = self._clock()
        try:
            state, failure = await self._event_flights.run(
                symbol, lambda: self._refresh_events(symbol)
            )
        except ProviderError as exc:
            reason = (
                f"Corporate events are unavailable: {describe_failure(exc)}. "
                "Earnings, dividend and split markers are hidden for now."
            )
            return [], DataStatus(state="unavailable", as_of=None, reason=reason)
        today = now.astimezone(UTC).date()
        events = await self._events.get_range(
            symbol, today - timedelta(days=EVENTS_START_DAYS), today
        )
        return events, _status("Corporate event data", "events", state, now, failure)

    async def company_name(self, symbol: str) -> str:
        """The quote's name, or the bare ticker when no quote can be had."""
        try:
            quote, _ = await self.quote(symbol)
        except AppError:
            return root_ticker(symbol)
        return quote.name

    async def _refresh_events(self, symbol: str) -> tuple[EventsFetchState, ProviderError | None]:
        """Refresh the saved events if stale (the body of one single flight per symbol)."""
        now = self._clock()
        today = now.astimezone(UTC).date()
        start = today - timedelta(days=EVENTS_START_DAYS)

        async def fetch() -> EventsFetchState:
            begin = datetime(start.year, start.month, start.day, tzinfo=UTC)
            until = datetime(today.year, today.month, today.day, tzinfo=UTC)
            fetched = await self._provider.events(symbol, begin, until)
            return await self._events.upsert_many(
                symbol, fetched, start=start, end=today, fetched_at=now
            )

        state = await self._events.get_state(symbol)
        stale = (
            state is None
            or now - state.last_fetched_at > EVENTS_REFRESH_AFTER
            or state.covered_start > start + COVERAGE_SLACK
        )
        return await self._refresh("events", symbol, state, stale, fetch)

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
