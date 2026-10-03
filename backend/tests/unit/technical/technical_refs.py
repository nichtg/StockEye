"""Independent reference implementations used only by the technical-analysis tests.

Deliberately written as plain Python loops over lists, with no pandas and no import from
``app``, so they cannot share a bug with the code under test.
"""

from __future__ import annotations

import math
import statistics

import pandas as pd
from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

NAN = float("nan")


def frame(bars: list[tuple[float, float, float, float]], volume: float = 1000.0) -> pd.DataFrame:
    """Daily frame from (open, high, low, close) tuples on consecutive business days."""
    idx = pd.bdate_range("2024-01-01", periods=len(bars))
    return pd.DataFrame(
        {
            "open": [b[0] for b in bars],
            "high": [b[1] for b in bars],
            "low": [b[2] for b in bars],
            "close": [b[3] for b in bars],
            "volume": [volume] * len(bars),
        },
        index=idx,
    )


def ref_sma(x: list[float], n: int) -> list[float]:
    return [NAN if i < n - 1 else sum(x[i - n + 1 : i + 1]) / n for i in range(len(x))]


def ref_ema(x: list[float], n: int) -> list[float]:
    out = [NAN] * len(x)
    if len(x) < n:
        return out
    out[n - 1] = sum(x[:n]) / n
    k = 2.0 / (n + 1)
    for i in range(n, len(x)):
        out[i] = x[i] * k + out[i - 1] * (1 - k)
    return out


def ref_macd(
    x: list[float], fast: int, slow: int, sig: int
) -> tuple[list[float], list[float], list[float]]:
    f, s = ref_ema(x, fast), ref_ema(x, slow)
    line = [a - b for a, b in zip(f, s, strict=True)]
    start = next(i for i, v in enumerate(line) if not math.isnan(v))
    tail = ref_ema(line[start:], sig)
    signal = [NAN] * start + tail
    hist = [a - b for a, b in zip(line, signal, strict=True)]
    return line, signal, hist


def ref_rsi(x: list[float], n: int) -> list[float]:
    out = [NAN] * len(x)
    ch = [x[i] - x[i - 1] for i in range(1, len(x))]
    if len(ch) < n:
        return out
    g = sum(max(c, 0.0) for c in ch[:n]) / n
    lo = sum(max(-c, 0.0) for c in ch[:n]) / n
    for i in range(n, len(x)):
        if i > n:
            c = ch[i - 1]
            g = (g * (n - 1) + max(c, 0.0)) / n
            lo = (lo * (n - 1) + max(-c, 0.0)) / n
        if g == 0 and lo == 0:
            out[i] = 50.0
        elif lo == 0:
            out[i] = 100.0
        else:
            out[i] = 100 - 100 / (1 + g / lo)
    return out


def ref_atr(h: list[float], low: list[float], c: list[float], n: int) -> list[float]:
    tr = [h[0] - low[0]] + [
        max(h[i] - low[i], abs(h[i] - c[i - 1]), abs(low[i] - c[i - 1])) for i in range(1, len(c))
    ]
    out = [NAN] * len(c)
    if len(c) < n:
        return out
    out[n - 1] = sum(tr[:n]) / n
    for i in range(n, len(c)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def ref_bollinger(x: list[float], n: int, k: float) -> list[tuple[float, float, float]]:
    out: list[tuple[float, float, float]] = []
    for i in range(len(x)):
        if i < n - 1:
            out.append((NAN, NAN, NAN))
            continue
        w = x[i - n + 1 : i + 1]
        m, s = statistics.fmean(w), statistics.pstdev(w)
        out.append((m, m + k * s, m - k * s))
    return out


def ref_wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Closed-form Wilson bounds in the (2np + z^2 +/- z*sqrt(...)) / (2(n + z^2)) form."""
    p = successes / n
    root = z * math.sqrt(z * z + 4 * n * p * (1 - p))
    return (
        (2 * n * p + z * z - root) / (2 * (n + z * z)),
        (2 * n * p + z * z + root) / (2 * (n + z * z)),
    )


def ohlc_frames(min_size: int = 30, max_size: int = 60) -> SearchStrategy[pd.DataFrame]:
    """Hypothesis strategy: valid random OHLCV frames (high >= max(o,c), low <= min(o,c))."""
    price = st.floats(min_value=5.0, max_value=300.0, allow_nan=False, allow_infinity=False)
    wick = st.floats(min_value=0.0, max_value=15.0, allow_nan=False, allow_infinity=False)
    bar = st.tuples(price, price, wick, wick).map(
        lambda t: (t[0], max(t[0], t[1]) + t[2], max(0.01, min(t[0], t[1]) - t[3]), t[1])
    )
    return st.lists(bar, min_size=min_size, max_size=max_size).map(frame)
