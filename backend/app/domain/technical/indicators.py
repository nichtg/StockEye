"""Technical indicators. Every function returns a Series/DataFrame aligned to the input index.

Warm-up rows are NaN. Value at row ``t`` depends only on rows ``<= t`` (no look-ahead).
Smoothing conventions match TA-Lib / TradingView (SMA-seeded EMA, Wilder RSI/ATR).
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

FloatArray = np.ndarray[tuple[int], np.dtype[np.float64]]


def _check_period(period: int) -> None:
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")


def _as_array(series: pd.Series) -> FloatArray:
    return np.asarray(series.to_numpy(dtype=float), dtype=np.float64)


def _ema_array(values: FloatArray, period: int) -> FloatArray:
    """EMA seeded with the SMA of the first ``period`` non-NaN values.

    Leading NaNs are skipped, which is how the MACD signal line gets its own warm-up.
    """
    out = np.full(values.shape, np.nan, dtype=np.float64)
    valid = np.flatnonzero(~np.isnan(values))
    if valid.size == 0:
        return out
    first = int(valid[0])
    seed = first + period - 1
    if seed >= values.size:
        return out
    out[seed] = values[first : seed + 1].mean()
    alpha = 2.0 / (period + 1)
    for i in range(seed + 1, values.size):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


def _wilder(values: FloatArray, period: int, seed_index: int) -> FloatArray:
    """Wilder smoothing, seeded at ``seed_index`` with the mean of the ``period`` values to it."""
    out = np.full(values.shape, np.nan, dtype=np.float64)
    if seed_index >= values.size:
        return out
    out[seed_index] = values[seed_index - period + 1 : seed_index + 1].mean()
    for i in range(seed_index + 1, values.size):
        out[i] = (out[i - 1] * (period - 1) + values[i]) / period
    return out


def sma(close: pd.Series, period: int) -> pd.Series:
    """Simple moving average over ``period`` rows; NaN for the first ``period - 1`` rows."""
    _check_period(period)
    return close.astype(float).rolling(window=period, min_periods=period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    """Exponential moving average, alpha = 2/(period+1), seeded with the first-period SMA."""
    _check_period(period)
    return pd.Series(_ema_array(_as_array(close), period), index=close.index)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI in [0, 100]; the first ``period`` rows are NaN.

    Flat windows (no gains, no losses) give 50; gains with no losses give 100.
    """
    _check_period(period)
    x = _as_array(close)
    out = np.full(x.shape, np.nan, dtype=np.float64)
    if x.size <= period:
        return pd.Series(out, index=close.index)
    delta = np.diff(x)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = float(gain[:period].mean())
    avg_loss = float(loss[:period].mean())
    for i in range(period, x.size):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gain[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + loss[i - 1]) / period
        if avg_loss == 0.0:
            out[i] = 100.0 if avg_gain > 0.0 else 50.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return pd.Series(out, index=close.index)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD line (fast EMA - slow EMA), signal line (EMA of the MACD line) and histogram."""
    _check_period(fast)
    _check_period(slow)
    _check_period(signal)
    x = _as_array(close)
    line = _ema_array(x, fast) - _ema_array(x, slow)
    sig = _ema_array(line, signal)
    return pd.DataFrame(
        {"macd": line, "signal": sig, "histogram": line - sig},
        index=close.index,
    )


def bollinger(close: pd.Series, period: int = 20, k: float = 2.0) -> pd.DataFrame:
    """Bollinger bands: SMA +/- k * population standard deviation (ddof=0)."""
    _check_period(period)
    roll = close.astype(float).rolling(window=period, min_periods=period)
    middle = roll.mean()
    std = roll.std(ddof=0)
    return pd.DataFrame(
        {"middle": middle, "upper": middle + k * std, "lower": middle - k * std},
        index=close.index,
    )


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average true range with Wilder smoothing; first ``period - 1`` rows are NaN.

    The first bar's true range is high - low (no previous close exists).
    """
    _check_period(period)
    high = _as_array(df["high"])
    low = _as_array(df["low"])
    close = _as_array(df["close"])
    tr = high - low
    if tr.size > 1:
        prev = close[:-1]
        tr[1:] = np.maximum.reduce(
            [high[1:] - low[1:], np.abs(high[1:] - prev), np.abs(low[1:] - prev)]
        )
    return pd.Series(_wilder(tr, period, period - 1), index=df.index)


def _cum_vwap(df: pd.DataFrame, groups: pd.Series | None) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"]
    vol = df["volume"]
    if groups is None:
        cum_pv, cum_v = pv.cumsum(), vol.cumsum()
    else:
        cum_pv, cum_v = pv.groupby(groups).cumsum(), vol.groupby(groups).cumsum()
    return (cum_pv / cum_v.where(cum_v > 0)).astype(float)


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """Intraday VWAP over typical price, cumulative and reset at each calendar date.

    The index must be exchange-local naive timestamps so that "date" is the session date.
    NaN while cumulative session volume is zero.
    """
    groups = pd.Series(pd.DatetimeIndex(df.index).normalize(), index=df.index)
    return _cum_vwap(df, groups)


def anchored_vwap(df: pd.DataFrame, anchor: datetime | pd.Timestamp) -> pd.Series:
    """VWAP accumulated from the first row at or after ``anchor``; NaN before it."""
    mask = df.index >= pd.Timestamp(anchor)
    out = pd.Series(np.nan, index=df.index, dtype=float)
    if mask.any():
        out[mask] = _cum_vwap(df.loc[mask], None)
    return out
