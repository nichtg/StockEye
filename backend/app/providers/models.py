"""Normalized data shapes every provider adapter returns.

Adapters translate each vendor's payload into these models, so nothing downstream
ever sees a vendor-specific field. All datetimes are timezone-aware UTC.
"""

from datetime import date, datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator

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

    @field_validator("website")
    @classmethod
    def _web_url_only(cls, value: str | None) -> str | None:
        """Keep only an absolute http(s) URL with a host: it is rendered as a link."""
        if value is None:
            return None
        try:
            parts = urlsplit(value.strip())
            host = parts.hostname
        except ValueError:
            return None
        return urlunsplit(parts) if parts.scheme in {"http", "https"} and host else None


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


class ScreenQuery(_Frozen):
    """A Yahoo screener request. Money fields are in the region's own currency."""

    region: Literal["us", "sg"]
    min_market_cap: float
    max_market_cap: float
    min_avg_volume: int  # shares per day, 3-month average; at least this many
    max_pe: float | None = None  # when set, a trailing P/E above 0 and at most this is required
    sort_field: str
    sort_asc: bool
    size: int = Field(ge=1, le=25)


class ScreenMatch(_Frozen):
    """One screener hit; numbers are None when Yahoo sent nothing usable."""

    symbol: str
    name: str
    exchange: Exchange
    currency: str | None
    market_cap: float | None
    pe_ratio: float | None
    price: float | None
    avg_volume_3m: float | None = None  # shares per day, 3-month average
