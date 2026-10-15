"""Chart construction: full-history candles, indicator series and markers. Pure; no I/O.

The chart carries every row of the interval's history so the user can pan and zoom left of the
chosen range. The range only decides ``visible_from`` (where the view starts). Indicators are
computed on the full frame and warm-up NaNs are dropped, so lines simply start later.
"""

import math
from datetime import date
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
from app.providers.models import CorporateEvent, Interval
from app.services.reports import Candle, Marker, RangeKey, SeriesPoint

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


def visible_start(frame: pd.DataFrame, range_key: RangeKey) -> pd.Timestamp:
    """Index label of the first row of the chosen range (the left edge of the initial view).

    Hourly: the first bar of the Nth-last session. Daily: the first bar within N calendar days
    of the last bar.
    """
    interval, span = RANGES[range_key]
    index = pd.DatetimeIndex(frame.index)
    if interval == "1h":
        days = index.normalize().unique()
        first = days[max(0, len(days) - span)]
        return pd.Timestamp(index[index.normalize() >= first][0])
    return pd.Timestamp(index[index >= index[-1] - pd.Timedelta(days=span)][0])


def candles(frame: pd.DataFrame, interval: Interval, tz: ZoneInfo) -> list[Candle]:
    stamps = pd.DatetimeIndex(frame.index)
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
            frame["open"],
            frame["high"],
            frame["low"],
            frame["close"],
            frame["volume"],
            strict=True,
        )
    ]


def _points(series: pd.Series, interval: Interval, tz: ZoneInfo) -> list[SeriesPoint]:
    out: list[SeriesPoint] = []
    for stamp, value in zip(pd.DatetimeIndex(series.index), series, strict=True):
        number = float(value)
        if math.isfinite(number):  # warm-up NaNs (and any infinity) never reach the chart
            out.append(SeriesPoint(time=time_of(stamp, interval, tz), value=number))
    return out


def indicator_series(
    frame: pd.DataFrame,
    visible_from: pd.Timestamp,
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
                # anchor is the left edge of the chosen range (``visible_from``), not the first
                # row of the history.
                if interval == "1h":
                    columns[name] = session_vwap(frame)
                else:
                    columns[name] = anchored_vwap(frame, visible_from)
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
    return {key: _points(col, interval, tz) for key, col in columns.items()}


def _time_by_date(frame: pd.DataFrame, interval: Interval, tz: ZoneInfo) -> dict[date, Time]:
    """Date -> chart time of that day's first bar (markers attach to a bar)."""
    out: dict[date, Time] = {}
    for stamp in pd.DatetimeIndex(frame.index):
        out.setdefault(stamp.date(), time_of(stamp, interval, tz))
    return out


def build_markers(
    frame: pd.DataFrame,
    interval: Interval,
    tz: ZoneInfo,
    *,
    events: list[CorporateEvent],
    hits: list[PatternHit],
    news: list[tuple[date, str, float]],
) -> list[Marker]:
    """Event, pattern and news markers that fall on a bar of ``frame`` (all history).

    ``news`` is (session date, headline, car_0_1). Pattern ``hits`` are only passed for daily
    ranges and are matched to bars by date. Values are deliberately unrounded: penny stocks
    (about S$0.012) would otherwise lose their indicator shape.
    """
    at = _time_by_date(frame, interval, tz)
    markers: list[Marker] = []
    for event in events:
        if event.date in at:
            markers.append(Marker(time=at[event.date], kind=event.kind, label=event.label))
    for hit in hits:
        # Hits come from this same frame, so their date always has a bar.
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
