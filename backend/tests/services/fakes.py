"""In-memory stand-ins for the vendor seams, so service tests need no network."""

import asyncio
import zlib
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import numpy as np

from app.config import Settings
from app.db import Database
from app.providers.errors import ProviderError, QuotaExhaustedError, SymbolNotFoundError
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
from app.providers.resilience import ProviderGuard
from app.repositories.ingest_budget import IngestBudget
from app.repositories.quotas import QuotaLedger
from app.sentiment.scorer import SentimentScore, SentimentUnavailableError
from app.services.admission import NewSymbolAdmission
from app.services.analysis import AnalysisService
from app.services.calendars import exchange_for, session_calendar
from app.services.container import Services
from app.services.market_data import MarketDataService
from app.services.news import NewsService

# Saturday: both exchanges closed, last completed session is Friday 2026-10-02.
CLOSED_NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
# Friday 15:00 UTC: NYSE is mid-session (open 13:30-20:00 UTC), Thursday is the last completed day.
OPEN_NOW = datetime(2026, 10, 2, 15, 0, tzinfo=UTC)

NAMES = {
    "AAPL": "Apple Inc.",
    "D05.SI": "DBS Group Holdings Ltd",
    "SPY": "SPDR S&P 500 ETF Trust",
    "^STI": "STI Index",
    "MSFT": "Microsoft Corporation",
}


class FakeClock:
    def __init__(self, now: datetime = CLOSED_NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeMarketData:
    """Deterministic random-walk prices on the real exchange calendar."""

    name = "yahoo"

    def __init__(self, clock: FakeClock, unknown: Sequence[str] = ("ZZZZ",)) -> None:
        self._clock = clock
        self.unknown = set(unknown)
        self.fail_with: ProviderError | None = None
        self.fail_symbols: dict[str, ProviderError] = {}
        self.empty_bars = False  # answer bar requests with an empty list, like a vendor glitch
        self.calls: dict[str, int] = {"search": 0, "quote": 0, "bars": 0, "events": 0}

    def _check(self, symbol: str) -> None:
        if symbol in self.unknown:
            raise SymbolNotFoundError(self.name, f"unknown symbol {symbol}")
        if symbol in self.fail_symbols:
            raise self.fail_symbols[symbol]
        if self.fail_with is not None:
            raise self.fail_with

    async def search(self, query: str) -> list[SymbolMatch]:
        self.calls["search"] += 1
        self._check(query.upper())
        return [
            SymbolMatch(symbol=s, name=n, exchange=exchange_for(s))
            for s, n in NAMES.items()
            if query.lower() in s.lower() or query.lower() in n.lower()
        ]

    async def quote(self, symbol: str) -> Quote:
        self.calls["quote"] += 1
        self._check(symbol)
        bars = self._daily(symbol, date(2025, 1, 1), self._clock().date())
        return Quote(
            symbol=symbol,
            name=NAMES.get(symbol, symbol),
            exchange=exchange_for(symbol),
            currency="SGD" if symbol.endswith(".SI") else "USD",
            price=bars[-1].close,
            previous_close=bars[-2].close,
            as_of=self._clock(),
        )

    def _daily(self, symbol: str, start: date, end: date) -> list[Bar]:
        cal = session_calendar(symbol, start, end)
        rng = np.random.default_rng(zlib.crc32(symbol.encode()))
        steps = rng.normal(0.0004, 0.012, len(cal.sessions))
        price = 100.0
        bars: list[Bar] = []
        for session, step in zip(cal.sessions, steps, strict=True):
            close = price * float(np.exp(step))
            bars.append(
                Bar(
                    ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
                    open=price,
                    high=max(price, close) * 1.004,
                    low=min(price, close) * 0.996,
                    close=close,
                    volume=1_000_000.0,
                )
            )
            price = close
        return bars

    async def bars(
        self, symbol: str, interval: Interval, start: datetime, end: datetime
    ) -> list[Bar]:
        self.calls["bars"] += 1
        self._check(symbol)
        if self.empty_bars:
            return []
        today = self._clock().date()  # the in-progress session's bar is included, like Yahoo
        last_day = min(end.date(), today)
        daily = self._daily(symbol, start.date(), last_day)
        if interval == "1d":
            return daily
        cal = session_calendar(symbol, start.date(), last_day)
        out: list[Bar] = []
        for bar, close_at in zip(daily, cal.closes_utc, strict=True):
            for hours_before_close in range(7, 0, -1):
                ts = close_at - timedelta(hours=hours_before_close)
                if ts <= self._clock():
                    out.append(bar.model_copy(update={"ts": ts}))
        return out

    async def events(self, symbol: str, start: datetime, end: datetime) -> list[CorporateEvent]:
        self.calls["events"] += 1
        self._check(symbol)
        cal = session_calendar(symbol, start.date(), end.date())
        out: list[CorporateEvent] = []
        for i, session in enumerate(cal.sessions):
            if i % 63 == 10:
                out.append(CorporateEvent(kind="earnings", date=session, label="Earnings"))
            if i % 63 == 40:
                out.append(
                    CorporateEvent(
                        kind="dividend", date=session, label="Dividend 0.25 USD", value=0.25
                    )
                )
        return out


class FakeNews:
    """Several articles per window; some irrelevant, some duplicated across windows."""

    def __init__(
        self,
        name: str = "google_news",
        exchanges: frozenset[Exchange] = frozenset({"US", "SGX"}),
    ) -> None:
        self.name = name
        self.exchanges = exchanges
        self.queries: list[NewsQuery] = []
        self.fail_windows: set[str] = set()  # "YYYY-MM" of the window start
        self.fail_with: ProviderError | None = None
        self.quota_hits = 0  # next N fetches raise QuotaExhaustedError
        self.quota_window = "minute"
        self.active = 0  # fetches in flight right now, and the most there ever were
        self.max_active = 0

    async def fetch(self, query: NewsQuery) -> list[NewsItem]:
        self.queries.append(query)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0)  # a real fetch yields to the loop; overlap shows in max_active
            return self._answer(query)
        finally:
            self.active -= 1

    def _answer(self, query: NewsQuery) -> list[NewsItem]:
        if self.fail_with is not None:
            raise self.fail_with
        if self.quota_hits:
            self.quota_hits -= 1
            raise QuotaExhaustedError(
                self.name,
                f"{self.quota_window} quota exhausted",
                window=self.quota_window,
                retry_at=CLOSED_NOW + timedelta(seconds=20),
            )
        key = query.start.strftime("%Y-%m")
        if query.end - query.start > timedelta(days=20) and key in self.fail_windows:
            raise ProviderError(self.name, "window failed")
        core = query.company_name.split()[0]
        items: list[NewsItem] = []
        for n in range(8):
            when = query.start + timedelta(days=3 * n + 1, hours=n)
            if when >= query.end:
                break
            items.append(
                _item(f"{core} reports update number {when:%Y%m%d%H} on strategy", when, self.name)
            )
        mid = query.start + timedelta(days=2)
        items.append(_item("Local orchard harvest hits a record this autumn", mid, self.name))
        if items:
            # Same story re-published by the same source: must collapse into one document.
            first = items[0]
            items.append(_item(first.title.upper() + "!", first.published_at, self.name))
        return items


def _item(title: str, when: datetime, provider: str) -> NewsItem:
    slug = abs(zlib.crc32(f"{title}{when}".encode()))
    return NewsItem.model_validate(
        {
            "url": f"https://news.example.com/{slug}",
            "title": title,
            "summary": "Analysts weigh in on the outlook.",
            "source": "Example Wire",
            "published_at": when,
            "provider": provider,
        }
    )


class FakeScorer:
    model_version = "fake-1"

    def __init__(self) -> None:
        self.available = True
        self.batches: list[int] = []

    def score(self, texts: Sequence[str]) -> list[SentimentScore]:
        if not self.available:
            raise SentimentUnavailableError("FinBERT model unavailable: missing model.onnx")
        self.batches.append(len(texts))
        out: list[SentimentScore] = []
        for text in texts:
            value = (zlib.crc32(text.encode()) % 100) / 100.0  # 0..0.99, stable per text
            positive, negative = value * 0.8, (1.0 - value) * 0.8
            out.append(SentimentScore(positive, negative, 1.0 - positive - negative))
        return out


def build_fake_services(
    db: Database,
    settings: Settings,
    *,
    clock: FakeClock,
    provider: FakeMarketData,
    news_provider: FakeNews,
    scorer: FakeScorer,
) -> Services:
    """Real services over the fake vendors. The guard only backs the admin status page."""
    guard = ProviderGuard(
        QuotaLedger(db), settings.provider_limits, settings.quota_warning_ratio, clock=clock
    )
    market = MarketDataService(db, provider, clock)
    news = NewsService(db, news_provider, [news_provider], scorer, clock=clock)
    admission = NewSymbolAdmission(
        IngestBudget(db, settings.max_new_symbols_per_user_per_day), news, clock
    )
    analysis = AnalysisService(db, market, news, admission, clock)
    return Services(market, news, analysis, admission, guard)
