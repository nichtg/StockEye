"""Exchange calendars: which sessions exist, when they close, and whether one is open now."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xc
import pandas as pd

from app.domain.macro import SessionCalendar
from app.providers.models import Exchange

_LOOKBACK_DAYS = 10  # longer than any holiday run, so a completed session is always in view


@dataclass(frozen=True)
class ExchangeSpec:
    exchange: Exchange
    calendar_name: str
    timezone: str
    benchmarks: tuple[str, ...]  # tried in order; the first with data wins


SPECS: dict[Exchange, ExchangeSpec] = {
    "SGX": ExchangeSpec("SGX", "XSES", "Asia/Singapore", ("^STI", "ES3.SI")),
    "US": ExchangeSpec("US", "XNYS", "America/New_York", ("SPY",)),
}


_SGX_INDEXES = frozenset({"^STI"})  # Straits Times Index has no ".SI" suffix


def exchange_for(symbol: str) -> Exchange:
    upper = symbol.upper()
    return "SGX" if upper.endswith(".SI") or upper in _SGX_INDEXES else "US"


def root_ticker(symbol: str) -> str:
    """The ticker without the exchange suffix, upper-cased: "d05.si" -> "D05"."""
    return symbol.upper().removesuffix(".SI")


def spec_for(symbol: str) -> ExchangeSpec:
    return SPECS[exchange_for(symbol)]


def exchange_tz(symbol: str) -> ZoneInfo:
    return ZoneInfo(spec_for(symbol).timezone)


@lru_cache(maxsize=4)
def _calendar(name: str) -> xc.ExchangeCalendar:
    # Building a calendar takes about a second, so it is built once per process.
    return xc.get_calendar(name)


def _schedule(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Schedule rows (index = session date, ``open``/``close`` in UTC) within [start, end]."""
    sched: pd.DataFrame = _calendar(spec_for(symbol).calendar_name).schedule
    return sched.loc[pd.Timestamp(start) : pd.Timestamp(end)]


def session_calendar(symbol: str, start: date, end: date) -> SessionCalendar:
    """Sessions in [start, end] with their UTC close times. Clipped to the calendar's range."""
    sched = _schedule(symbol, start, end)
    return SessionCalendar(
        sessions=tuple(ts.date() for ts in sched.index),
        closes_utc=tuple(ts.to_pydatetime() for ts in sched["close"]),
    )


def _around(symbol: str, now: datetime) -> pd.DataFrame:
    day = now.astimezone(UTC).date()
    return _schedule(symbol, day - timedelta(days=_LOOKBACK_DAYS), day + timedelta(days=1))


def is_session_open(symbol: str, now: datetime) -> bool:
    """True while a regular session is in progress (a lunch break still counts as open)."""
    stamp = pd.Timestamp(now.astimezone(UTC))
    sched = _around(symbol, now)
    return bool(((sched["open"] <= stamp) & (stamp < sched["close"])).any())


def last_completed_session(symbol: str, now: datetime) -> date:
    """Date of the most recent session whose close is at or before ``now``."""
    stamp = pd.Timestamp(now.astimezone(UTC))
    sched = _around(symbol, now)
    done = sched[sched["close"] <= stamp]
    if done.empty:
        raise LookupError(f"no completed session near {now.isoformat()} for {symbol}")
    last: date = done.index[-1].date()
    return last


def session_close(symbol: str, session: date) -> datetime | None:
    """UTC close time of ``session``, or None if the exchange was shut that day."""
    sched = _schedule(symbol, session, session)
    return None if sched.empty else sched["close"].iloc[0].to_pydatetime()
