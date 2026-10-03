"""Market data use-cases: quotes, search, price bars and corporate events, cache-first.

The provider is already guarded (see ``ProviderGuard.wrap_market``). A provider failure never
becomes a 500: the service falls back to whatever is saved and says so in a ``DataStatus``. The
only hard failures are an unknown symbol (404) and "nothing saved and the provider is down" for
prices (503).
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from app.db import Database
from app.logging_setup import get_logger
from app.providers.base import MarketDataProvider
from app.providers.errors import ProviderError, SymbolNotFoundError
from app.providers.models import Bar, CorporateEvent, Interval, Quote, SymbolMatch
from app.repositories.bars import BarsRepository, FetchState
from app.repositories.cache import CacheRepository
from app.repositories.events import EventsRepository
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


def _unavailable(what: str, symbol: str, exc: ProviderError | None) -> AppError:
    cause = f" ({describe_failure(exc)})" if exc else ""
    return AppError(
        503,
        "data_unavailable",
        f"{what} for {symbol} is temporarily unavailable{cause} and nothing has been saved yet. "
        "Please try again in a few minutes.",
    )


def _not_found(symbol: str) -> AppError:
    return AppError(404, "not_found", f"We could not find a stock with the symbol {symbol}.")


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
        now = self._clock()
        key = f"quote:{symbol}"
        if (cached := await self._cache.get(key, now)) is not None:
            quote = Quote.model_validate(cached)
            return quote, ok(quote.as_of)
        try:
            quote = await self._provider.quote(symbol)
        except SymbolNotFoundError as exc:
            raise _not_found(symbol) from exc
        except ProviderError as exc:
            stale = await self._cache.get_stale(key)
            if stale is None:
                raise _unavailable("The price quote", symbol, exc) from exc
            payload, created = stale
            log.warning("quote_stale_fallback", symbol=symbol, error=str(exc))
            return Quote.model_validate(payload), stale_status(
                "Price quote", "quote", created, now, exc
            )
        await self._cache.put(key, quote.model_dump(mode="json"), QUOTE_TTL, now)
        return quote, ok(quote.as_of)

    async def search(self, query: str) -> list[SymbolMatch]:
        text = query.strip()
        if not text:
            return []
        now = self._clock()
        key = f"search:{text.lower()}"
        if (cached := await self._cache.get(key, now)) is not None:
            return [SymbolMatch.model_validate(m) for m in cached["matches"]]
        try:
            matches = await self._provider.search(text)
        except ProviderError as exc:
            stale = await self._cache.get_stale(key)
            if stale is not None:
                return [SymbolMatch.model_validate(m) for m in stale[0]["matches"]]
            raise _unavailable("Stock search", text, exc) from exc
        payload = {"matches": [m.model_dump(mode="json") for m in matches]}
        await self._cache.put(key, payload, SEARCH_TTL, now)
        return matches

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
        state = await self._bars.get_state(symbol, interval)
        failure: ProviderError | None = None
        if self._needs_refresh(symbol, interval, state, start, now):
            try:
                fetched = await self._provider.bars(symbol, interval, start, end)
            except SymbolNotFoundError as exc:
                raise _not_found(symbol) from exc
            except ProviderError as exc:
                failure = exc
                log.warning("bars_fetch_failed", symbol=symbol, interval=interval, error=str(exc))
            else:
                await self._bars.replace_range(
                    symbol, interval, fetched, start=start, end=end, fetched_at=now
                )
                state = await self._bars.get_state(symbol, interval)
        stored = await self._bars.get_range(symbol, interval, start, end)
        bars = self._completed(symbol, interval, stored, now)
        if not bars:
            if failure is not None:
                raise _unavailable("Price data", symbol, failure)
            raise _not_found(symbol)
        if failure is not None and state is not None:
            return bars, stale_status("Price data", "prices", state.last_fetched_at, now, failure)
        return bars, ok(state.last_fetched_at if state else now)

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
        state = await self._events.get_state(symbol)
        failure: ProviderError | None = None
        stale = (
            state is None
            or now - state.last_fetched_at > EVENTS_REFRESH_AFTER
            or state.covered_start > start + COVERAGE_SLACK
        )
        if stale:
            begin = datetime(start.year, start.month, start.day, tzinfo=UTC)
            until = datetime(end.year, end.month, end.day, tzinfo=UTC)
            try:
                fetched = await self._provider.events(symbol, begin, until)
            except ProviderError as exc:
                failure = exc
                log.warning("events_fetch_failed", symbol=symbol, error=str(exc))
            else:
                await self._events.upsert_many(
                    symbol, fetched, start=start, end=end, fetched_at=now
                )
                state = await self._events.get_state(symbol)
        events = await self._events.get_range(symbol, start, end)
        if failure is None:
            return events, ok(state.last_fetched_at if state else now)
        if state is None:
            reason = (
                f"Corporate events are unavailable: {describe_failure(failure)}. "
                "Earnings, dividend and split markers are hidden for now."
            )
            return [], DataStatus(state="unavailable", as_of=None, reason=reason)
        return events, stale_status(
            "Corporate event data", "events", state.last_fetched_at, now, failure
        )
