"""YahooMarketData against a faked yfinance: no network."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, ClassVar

import pandas as pd
import pytest
import requests
import yfinance as yf
from structlog.testing import capture_logs
from yfinance.exceptions import YFRateLimitError, YFTickerMissingError

from app.providers.errors import (
    RateLimitedError,
    SymbolNotFoundError,
    TransientProviderError,
)
from app.providers.yahoo import YahooMarketData

START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 10, 1, tzinfo=UTC)


class FakeTicker:
    """Configurable stand-in for yf.Ticker; attributes are set per test."""

    fast: Any = SimpleNamespace(
        last_price=101.5, previous_close=100.0, currency="USD", exchange="NMS"
    )
    info: ClassVar[dict[str, Any]] = {"longName": "Apple Inc."}
    frame: pd.DataFrame = pd.DataFrame()
    dividends: pd.Series = pd.Series(dtype=float)
    splits: pd.Series = pd.Series(dtype=float)
    earnings: Any = None
    earnings_error: Exception | None = None
    history_error: Exception | None = None

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    @property
    def fast_info(self) -> Any:
        if isinstance(self.fast, Exception):
            raise self.fast
        return self.fast

    def history(self, **_: Any) -> pd.DataFrame:
        if self.history_error:
            raise self.history_error
        return self.frame

    def get_dividends(self) -> pd.Series:
        return self.dividends

    def get_splits(self) -> pd.Series:
        return self.splits

    def get_earnings_dates(self, limit: int = 12) -> Any:
        if self.earnings_error:
            raise self.earnings_error
        return self.earnings


@pytest.fixture
def ticker(monkeypatch: pytest.MonkeyPatch) -> type[FakeTicker]:
    """A fresh FakeTicker subclass per test so class-level overrides never leak."""
    cls = type("T", (FakeTicker,), {})
    monkeypatch.setattr(yf, "Ticker", cls)
    return cls


def _daily_frame(rows: list[tuple[str, float, float, float, float, float]]) -> pd.DataFrame:
    index = pd.DatetimeIndex([r[0] for r in rows], tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [r[5] for r in rows],
        },
        index=index,
    )


# --- search ----------------------------------------------------------------------------------


async def test_search_keeps_us_and_sgx_equities_and_etfs(monkeypatch: pytest.MonkeyPatch) -> None:
    quotes = [
        {
            "symbol": "D05.SI",
            "exchange": "SES",
            "quoteType": "EQUITY",
            "longname": "DBS Group Holdings Ltd",
            "shortname": "DBS",
        },
        {"symbol": "DBSDY", "exchange": "PNK", "quoteType": "EQUITY", "longname": "OTC DBS"},
        {"symbol": "SPY", "exchange": "PCX", "quoteType": "ETF", "shortname": "SPDR S&P 500"},
        {"symbol": "DBO", "exchange": "NYQ", "quoteType": "FUTURE", "longname": "Not equity"},
        {"symbol": "AAPL", "exchange": "NMS", "quoteType": "EQUITY"},  # no name at all
    ]

    class FakeSearch:
        def __init__(self, *_: Any, **__: Any) -> None:
            self.quotes = quotes

    monkeypatch.setattr(yf, "Search", FakeSearch)

    result = await YahooMarketData().search("dbs")

    assert [(m.symbol, m.name, m.exchange) for m in result] == [
        ("D05.SI", "DBS Group Holdings Ltd", "SGX"),
        ("SPY", "SPDR S&P 500", "US"),
    ]


async def test_search_returns_at_most_eight(monkeypatch: pytest.MonkeyPatch) -> None:
    many = [
        {"symbol": f"S{i}", "exchange": "NMS", "quoteType": "EQUITY", "longname": f"N{i}"}
        for i in range(12)
    ]

    class FakeSearch:
        def __init__(self, *_: Any, **__: Any) -> None:
            self.quotes = many

    monkeypatch.setattr(yf, "Search", FakeSearch)

    assert len(await YahooMarketData().search("s")) == 8


# --- quote -----------------------------------------------------------------------------------


async def test_quote_maps_fields(ticker: type[FakeTicker]) -> None:
    quote = await YahooMarketData().quote("AAPL")

    assert (quote.symbol, quote.name, quote.exchange, quote.currency) == (
        "AAPL",
        "Apple Inc.",
        "US",
        "USD",
    )
    assert (quote.price, quote.previous_close) == (101.5, 100.0)


async def test_quote_unknown_symbol_raises_symbol_not_found(ticker: type[FakeTicker]) -> None:
    # yfinance raises KeyError from fast_info when Yahoo has no metadata for the symbol.
    ticker.fast = KeyError("currentTradingPeriod")
    with pytest.raises(SymbolNotFoundError):
        await YahooMarketData().quote("ZZZZ")

    ticker.fast = YFTickerMissingError("ZZZZ", "no data")
    with pytest.raises(SymbolNotFoundError):
        await YahooMarketData().quote("ZZZZ")


async def test_quote_nan_price_raises_symbol_not_found(ticker: type[FakeTicker]) -> None:
    ticker.fast = SimpleNamespace(
        last_price=float("nan"), previous_close=1.0, currency="USD", exchange="NMS"
    )

    with pytest.raises(SymbolNotFoundError):
        await YahooMarketData().quote("ZZZZ")


async def test_quote_name_failure_falls_back_to_symbol(ticker: type[FakeTicker]) -> None:
    ticker.info = {}

    quote = await YahooMarketData().quote("D05.SI")

    assert quote.name == "D05.SI"


# --- bars ------------------------------------------------------------------------------------


async def test_bars_daily_uses_session_date_at_midnight_utc_and_drops_nan_rows(
    ticker: type[FakeTicker],
) -> None:
    nan = float("nan")
    ticker.frame = _daily_frame(
        [
            ("2026-09-01", 10, 11, 9, 10.5, 1000),
            ("2026-09-02", nan, nan, nan, nan, 0),
            ("2026-09-03", 10.5, 12, 10, 11.5, 2000),
        ]
    )

    bars = await YahooMarketData().bars("AAPL", "1d", START, END)

    assert [b.ts for b in bars] == [
        datetime(2026, 9, 1, tzinfo=UTC),
        datetime(2026, 9, 3, tzinfo=UTC),
    ]
    assert (bars[0].open, bars[0].high, bars[0].low, bars[0].close, bars[0].volume) == (
        10,
        11,
        9,
        10.5,
        1000,
    )


async def test_bars_hourly_converts_to_utc(ticker: type[FakeTicker]) -> None:
    index = pd.DatetimeIndex(["2026-09-28 09:30"], tz="America/New_York")
    ticker.frame = pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [10.0]}, index=index
    )

    bars = await YahooMarketData().bars("AAPL", "1h", START, END)

    assert bars[0].ts == datetime(2026, 9, 28, 13, 30, tzinfo=UTC)


async def test_bars_empty_result_is_empty_list(ticker: type[FakeTicker]) -> None:
    ticker.frame = pd.DataFrame()

    assert await YahooMarketData().bars("AAPL", "1d", START, END) == []


async def test_bars_rate_limit_maps_to_rate_limited_error(ticker: type[FakeTicker]) -> None:
    ticker.history_error = YFRateLimitError()

    with pytest.raises(RateLimitedError):
        await YahooMarketData().bars("AAPL", "1d", START, END)


async def test_bars_network_error_maps_to_transient(ticker: type[FakeTicker]) -> None:
    ticker.history_error = requests.ConnectionError("down")

    with pytest.raises(TransientProviderError):
        await YahooMarketData().bars("AAPL", "1d", START, END)


# --- events ----------------------------------------------------------------------------------


def _event_ticker(ticker: type[FakeTicker]) -> None:
    ticker.dividends = pd.Series(
        [0.24, 0.30],
        index=pd.DatetimeIndex(["2026-09-10 09:30", "2025-01-10 09:30"], tz="America/New_York"),
    )
    ticker.splits = pd.Series(
        [4.0, 0.1], index=pd.DatetimeIndex(["2026-09-15", "2026-09-20"], tz="America/New_York")
    )
    ticker.earnings = pd.DataFrame(
        {"EPS Estimate": [1.98, 1.5], "Reported EPS": [2.02, float("nan")]},
        index=pd.DatetimeIndex(["2026-09-25 16:00", "2026-09-28 16:00"], tz="America/New_York"),
    )


async def test_events_builds_dividend_split_and_earnings_in_range(
    ticker: type[FakeTicker],
) -> None:
    _event_ticker(ticker)

    events = await YahooMarketData().events("AAPL", START, END)

    assert [(e.kind, e.date.isoformat(), e.label, e.value) for e in events] == [
        ("dividend", "2026-09-10", "Dividend 0.24 USD", 0.24),
        ("split", "2026-09-15", "Split 4:1", 4.0),
        ("split", "2026-09-20", "Split 1:10", 0.1),
        ("earnings", "2026-09-25", "Earnings: EPS 2.02 vs est 1.98", 2.02),
        ("earnings", "2026-09-28", "Earnings", None),
    ]


async def test_events_earnings_failure_returns_the_rest_and_logs_warning(
    ticker: type[FakeTicker],
) -> None:
    _event_ticker(ticker)
    ticker.earnings_error = requests.ConnectionError("down")

    with capture_logs() as logs:
        events = await YahooMarketData().events("AAPL", START, END)

    assert {e.kind for e in events} == {"dividend", "split"}
    warnings = [entry for entry in logs if entry["log_level"] == "warning"]
    assert len(warnings) == 1
    assert warnings[0]["part"] == "earnings"


async def test_events_core_failure_propagates(ticker: type[FakeTicker]) -> None:
    ticker.fast = requests.ConnectionError("down")

    with pytest.raises(TransientProviderError):
        await YahooMarketData().events("AAPL", START, END)
