"""Synthetic builders with known answers for the macro tests (imported by the test modules)."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.domain.macro import EventResult, SessionCalendar

NY = ZoneInfo("America/New_York")
SGT = ZoneInfo("Asia/Singapore")


def make_calendar(
    start: date, n_sessions: int, tz: ZoneInfo = NY, close: time = time(16, 0)
) -> SessionCalendar:
    """Weekday-only calendar with one close per session at local ``close`` time."""
    days = pd.bdate_range(start, periods=n_sessions)
    sessions = tuple(d.date() for d in days)
    closes = tuple(datetime.combine(d, close, tzinfo=tz).astimezone(UTC) for d in sessions)
    return SessionCalendar(sessions=sessions, closes_utc=closes)


def build_market(
    n: int = 400,
    beta: float = 1.5,
    alpha: float = 0.0002,
    jumps: dict[int, float] | None = None,
    seed: int = 7,
) -> tuple[pd.Series, pd.Series, pd.DatetimeIndex]:
    """Stock = alpha + beta * bench (+ jumps). Noise-free, so OLS recovers beta exactly."""
    index = pd.bdate_range("2023-01-02", periods=n)
    rng = np.random.default_rng(seed)
    rm = rng.normal(0.0004, 0.01, n)
    rs = alpha + beta * rm
    for pos, jump in (jumps or {}).items():
        rs[pos] += jump
    rm[0] = rs[0] = 0.0  # position 0 has no return
    bench = pd.Series(100.0 * np.cumprod(1 + rm), index=index)
    stock = pd.Series(50.0 * np.cumprod(1 + rs), index=index)
    return stock, bench, index


def sent_frame(index: pd.DatetimeIndex, rows: dict[int, tuple[float, int]]) -> pd.DataFrame:
    """Daily sentiment frame from ``{position: (mean_score, article_count)}``."""
    positions = sorted(rows)
    return pd.DataFrame(
        {
            "mean_score": [rows[p][0] for p in positions],
            "article_count": [rows[p][1] for p in positions],
            "max_abs_score": [abs(rows[p][0]) for p in positions],
        },
        index=pd.DatetimeIndex([index[p] for p in positions]),
    )


def make_event(
    day: date,
    sentiment: float,
    car_0_1: float | None,
    *,
    car_0_5: float | None = None,
    car_pre_5: float | None = None,
    near_earnings: bool = False,
    ok: bool = True,
) -> EventResult:
    return EventResult(
        date=day,
        sentiment=sentiment,
        article_count=3,
        alpha=0.0 if ok else None,
        beta=1.0 if ok else None,
        car_0_0=car_0_1,
        car_0_1=car_0_1,
        car_0_5=car_0_5,
        car_pre_5=car_pre_5,
        near_earnings=near_earnings,
        status="ok" if ok else "insufficient_estimation",
    )
