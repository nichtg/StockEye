"""Normalized data shapes every provider adapter returns.

Adapters translate each vendor's payload into these models, so nothing downstream
ever sees a vendor-specific field. All datetimes are timezone-aware UTC.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, HttpUrl

Exchange = Literal["US", "SGX"]
Interval = Literal["1d", "1h"]
EventKind = Literal["earnings", "dividend", "split"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class SymbolMatch(_Frozen):
    symbol: str  # Yahoo-style ticker: "AAPL", "D05.SI"
    name: str
    exchange: Exchange


class Quote(_Frozen):
    symbol: str
    name: str
    exchange: Exchange
    currency: str
    price: float
    previous_close: float
    as_of: AwareDatetime

    @property
    def change_pct(self) -> float | None:
        """Move versus the previous close in percent; None when there is no previous close."""
        if not self.previous_close:
            return None
        return (self.price / self.previous_close - 1.0) * 100.0


class Bar(_Frozen):
    """One OHLCV candle, split- and dividend-adjusted.

    ``ts`` is the bar's start time in UTC. For daily bars it is the session date at 00:00 UTC.
    """

    ts: AwareDatetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class CorporateEvent(_Frozen):
    kind: EventKind
    date: date
    label: str  # human-readable, e.g. "Dividend 0.25 USD", "Split 4:1"
    value: float | None = None  # dividend amount, split ratio, or reported EPS


class CompanyProfile(_Frozen):
    """Descriptive facts about a company; each field is None when the vendor has no usable value."""

    description: str | None = None  # plain text, at most 4000 characters
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    website: str | None = None  # absolute http(s) URL with a host; never any other scheme
    employees: int | None = None
    market_cap: float | None = None  # in ``currency``
    pe_ratio: float | None = None  # trailing twelve months
    dividend_yield: float | None = None  # a fraction: 0.0428 means 4.28%
    week52_low: float | None = None  # in ``currency``
    week52_high: float | None = None
    avg_volume: float | None = None  # shares per day
    currency: str | None = None


class NewsItem(_Frozen):
    url: HttpUrl
    title: str
    summary: str | None
    source: str  # publisher, e.g. "The Business Times"
    published_at: AwareDatetime
    provider: str  # adapter name that fetched it


class NewsQuery(_Frozen):
    symbol: str
    exchange: Exchange  # adapters branch on this, never on the ticker's suffix
    company_name: str
    start: datetime
    end: datetime
