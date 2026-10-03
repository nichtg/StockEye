"""Chart construction: visible window, indicator series and markers. Pure; no I/O.

Indicators are computed on the full frame (which includes warm-up history before the visible
window) and trimmed afterwards, so lines start at the left edge instead of with NaN gaps.
"""

import math
from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo

import pandas as pd

from app.domain.technical import (
    PATTERNS,
    anchored_vwap,
    bollinger,
    ema,
    macd,
    rsi,
    session_vwap,
    sma,
)
from app.domain.technical.candlesticks import PatternHit
from app.providers.models import CorporateEvent
from app.services.reports import Candle, Marker, SeriesPoint

RangeKey = Literal["1W", "1M", "6M", "1Y", "2Y"]
Interval = Literal["1d", "1h"]
INDICATORS = ("sma20", "sma50", "ema9", "ema21", "vwap", "bollinger", "rsi", "macd")

# range -> (interval, hourly: number of sessions shown / daily: calendar days shown)
RANGES: dict[RangeKey, tuple[Interval, int]] = {
    "1W": ("1h", 5),
    "1M": ("1h", 22),
    "6M": ("1d", 183),
    "1Y": ("1d", 365),
    "2Y": ("1d", 730),
}

type Time = str | int


def time_of(stamp: pd.Timestamp, interval: Interval, tz: ZoneInfo) -> Time:
    """Chart time: "YYYY-MM-DD" for daily bars, UNIX seconds (UTC) for exchange-local hourly."""
    if interval == "1d":
        return stamp.strftime("%Y-%m-%d")
    return int(stamp.to_pydatetime().replace(tzinfo=tz).timestamp())


def visible_mask(frame: pd.DataFrame, range_key: RangeKey) -> pd.Series:
    """Boolean mask of the rows shown for ``range_key`` (the rest is indicator warm-up)."""
    interval, span = RANGES[range_key]
    index = pd.DatetimeIndex(frame.index)
    if interval == "1h":
        days = index.normalize().unique()
        first = days[max(0, len(days) - span)]
        keep = index.normalize() >= first
    else:
        keep = index >= index[-1] - pd.Timedelta(days=span)
    return pd.Series(keep, index=frame.index)


def candles(frame: pd.DataFrame, mask: pd.Series, interval: Interval, tz: ZoneInfo) -> list[Candle]:
    shown = frame[mask]
    stamps = pd.DatetimeIndex(shown.index)
    return [
        Candle(
            time=time_of(stamp, interval, tz),
            open=float(o),
            high=float(h),
            low=float(lo),
            close=float(c),
            volume=float(v),
        )
        for stamp, o, h, lo, c, v in zip(
            stamps,
            shown["open"],
            shown["high"],
            shown["low"],
            shown["close"],
            shown["volume"],
            strict=True,
        )
    ]


def _points(
    series: pd.Series, mask: pd.Series, interval: Interval, tz: ZoneInfo
) -> list[SeriesPoint]:
    out: list[SeriesPoint] = []
    shown = series[mask]
    for stamp, value in zip(pd.DatetimeIndex(shown.index), shown, strict=True):
        number = float(value)
        if not math.isnan(number):
            out.append(SeriesPoint(time=time_of(stamp, interval, tz), value=number))
    return out


def indicator_series(
    frame: pd.DataFrame,
    mask: pd.Series,
    names: list[str],
    interval: Interval,
    tz: ZoneInfo,
) -> dict[str, list[SeriesPoint]]:
    close = frame["close"]
    columns: dict[str, pd.Series] = {}
    for name in names:
        match name:
            case "sma20":
                columns[name] = sma(close, 20)
            case "sma50":
                columns[name] = sma(close, 50)
            case "ema9":
                columns[name] = ema(close, 9)
            case "ema21":
                columns[name] = ema(close, 21)
            case "vwap":
                # Intraday VWAP restarts every session; on daily bars the only meaningful
                # anchor is the left edge of what the user is looking at.
                if interval == "1h":
                    columns[name] = session_vwap(frame)
                else:
                    columns[name] = anchored_vwap(frame, frame.index[mask.to_numpy()][0])
            case "bollinger":
                bands = bollinger(close)
                for part in ("upper", "middle", "lower"):
                    columns[f"bollinger_{part}"] = bands[part]
            case "rsi":
                columns[name] = rsi(close)
            case "macd":
                lines = macd(close)
                columns["macd"] = lines["macd"]
                columns["macd_signal"] = lines["signal"]
                columns["macd_histogram"] = lines["histogram"]
    return {key: _points(col, mask, interval, tz) for key, col in columns.items()}


def _time_by_date(
    frame: pd.DataFrame, mask: pd.Series, interval: Interval, tz: ZoneInfo
) -> dict[date, Time]:
    """Date -> chart time of that day's first visible bar (markers attach to a bar)."""
    out: dict[date, Time] = {}
    for stamp in pd.DatetimeIndex(frame.index[mask.to_numpy()]):
        out.setdefault(stamp.date(), time_of(stamp, interval, tz))
    return out


def build_markers(
    frame: pd.DataFrame,
    mask: pd.Series,
    interval: Interval,
    tz: ZoneInfo,
    *,
    events: list[CorporateEvent],
    hits: list[PatternHit],
    news: list[tuple[date, str, float]],
) -> list[Marker]:
    """Event, pattern and news markers that fall on a visible bar.

    ``news`` is (session date, headline, car_0_1). Pattern ``hits`` are only passed for daily
    ranges; their ``index`` positions refer to ``frame``.
    """
    at = _time_by_date(frame, mask, interval, tz)
    markers: list[Marker] = []
    for event in events:
        if event.date in at:
            markers.append(Marker(time=at[event.date], kind=event.kind, label=event.label))
    visible_positions = {i for i, shown in enumerate(mask.to_numpy()) if shown}
    for hit in hits:
        if hit.index in visible_positions:
            spec = PATTERNS[hit.key]
            markers.append(
                Marker(
                    time=at[pd.Timestamp(hit.date).date()],
                    kind="pattern",
                    label=spec.label,
                    bias=spec.bias.value,
                    pattern=hit.key.value,
                )
            )
    for day, headline, car in news:
        if day in at:
            markers.append(Marker(time=at[day], kind="news", label=headline, car_0_1=round(car, 4)))
    return markers
