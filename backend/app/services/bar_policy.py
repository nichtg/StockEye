"""Pure rules for saved price bars: how far back they go, when they are stale, what is complete."""

from datetime import UTC, datetime, timedelta

from app.providers.models import Bar, Interval
from app.repositories.bars import FetchState
from app.services.calendars import (
    exchange_tz,
    is_session_open,
    last_completed_session,
    session_close,
)

# How far back each series is kept: 1d is 3 years (2 years of sessions + 200 warm-up), 1h is
# the 1M chart (22 sessions) plus indicator warm-up. One window per series, never per caller, is
# what lets concurrent callers share a single fetch.
HISTORY_DAYS: dict[Interval, int] = {"1d": 1100, "1h": 60}
REFRESH_AFTER = timedelta(minutes=15)
# Callers ask for a start date relative to "today", so the requested start creeps forward by a
# day each day. Without slack the stored coverage would look insufficient every morning.
COVERAGE_SLACK = timedelta(days=7)


def window_start(interval: Interval, now: datetime) -> datetime:
    """Start of the standard history for ``interval``: midnight UTC for daily bars."""
    start = now - timedelta(days=HISTORY_DAYS[interval])
    if interval == "1d":
        return start.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return start


def needs_refresh(
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


def completed(symbol: str, interval: Interval, bars: list[Bar], now: datetime) -> list[Bar]:
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
