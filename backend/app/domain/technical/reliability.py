"""Historical reliability of candlestick patterns on a single instrument.

Forward return for a hit at position ``t``: enter at ``open[t+1]`` (the next session's open,
the first price one could actually trade), exit at ``close[t+horizon]``. Hits whose exit bar
does not exist are dropped. Per pattern key, hits are made non-overlapping: a hit is skipped
when ``t - last_counted < horizon`` (its holding window would overlap the previous one).

The yardstick is a *conditional* base rate: how often the same forward return was up (or down)
over all eligible bars in the trend context the pattern requires. Comparing a reversal pattern
with the unconditional rate would credit it for mean reversion that any bar in that trend shows.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.domain.technical.candlestick_rules import PatternThresholds
from app.domain.technical.candlesticks import (
    DEFAULT_THRESHOLDS,
    PATTERNS,
    Bias,
    PatternHit,
    PatternKey,
    context_allows,
    trend_context,
)
from app.domain.technical.indicators import _validate_ohlcv


@dataclass(frozen=True, slots=True)
class PatternStats:
    key: PatternKey
    n: int
    up_count: int
    success_count: int | None
    hit_rate: float | None
    wilson_low: float | None
    wilson_high: float | None
    mean_return: float | None
    median_return: float | None
    base_up_rate: float | None  # P(forward ret > 0) over bars in the pattern's context
    base_rate: float | None  # base_up_rate if bullish, base_down_rate if bearish, else None
    edge: float | None
    sufficient: bool
    # Added after the first release; defaulted so existing constructors keep working.
    # Down-rate is P(ret < 0), NOT 1 - up-rate: exact-zero returns (ticks) are neither.
    base_down_rate: float | None = None
    base_n: int = 0  # eligible bars behind the base rates


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion; (0, 1) when ``n == 0``."""
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _forward_returns(
    df: pd.DataFrame, horizon: int
) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
    """Forward return per position; NaN where ``t + horizon`` is out of range."""
    o = df["open"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    n = len(df)
    out = np.full(n, np.nan, dtype=np.float64)
    for t in range(n - horizon):
        out[t] = c[t + horizon] / o[t + 1] - 1.0
    return out


def pattern_reliability(
    df: pd.DataFrame,
    hits: Sequence[PatternHit],
    horizon: int = 5,
    min_samples: int = 15,
    *,
    trend: pd.Series | None = None,
    thresholds: PatternThresholds = DEFAULT_THRESHOLDS,
) -> dict[PatternKey, PatternStats]:
    """Per-pattern forward-return statistics for every key present in ``hits``.

    ``base_up_rate`` / ``base_down_rate`` are the shares of eligible bars (forward return
    exists) with a positive / negative forward return, restricted to bars whose trend context
    satisfies the pattern's requirement (``PatternSpec.context``). ``edge`` is the success
    rate minus the matching base rate.

    The pattern's context is evaluated at its first candle ``s``. For base-rate bars each bar
    ``t`` is treated as a hypothetical single-candle pattern start (context at ``t`` uses bars
    ``<= t - 1``); the base rate asks "from a bar that has this prior trend, what happens over
    the next week?", which is the question a one-candle pattern answers exactly and a close
    approximation for two- and three-candle ones (their entry is later, their context earlier).

    ``trend`` may pass a precomputed ``trend_context(df)``. Raises ``ValueError`` on NaN prices
    or a non-increasing index.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    _validate_ohlcv(df)
    rets = _forward_returns(df, horizon)
    ctx = (trend if trend is not None else trend_context(df, thresholds)).to_numpy(dtype=object)
    if len(ctx) != len(rets):
        raise ValueError("trend context must have the same length as the price history")
    has_ret = ~np.isnan(rets)

    by_key: dict[PatternKey, list[PatternHit]] = {}
    for hit in sorted(hits, key=lambda h: h.index):
        by_key.setdefault(hit.key, []).append(hit)

    result: dict[PatternKey, PatternStats] = {}
    for key, key_hits in by_key.items():
        need = PATTERNS[key].context
        in_ctx = np.array([context_allows(need, v) for v in ctx], dtype=bool)
        base = rets[has_ret & in_ctx]
        base_up = float((base > 0).mean()) if base.size else None
        base_down = float((base < 0).mean()) if base.size else None
        counted: list[float] = []
        last: int | None = None
        for hit in key_hits:
            ret = rets[hit.index] if 0 <= hit.index < len(rets) else float("nan")
            if np.isnan(ret):
                continue
            if last is not None and hit.index - last < horizon:
                continue
            counted.append(float(ret))
            last = hit.index
        result[key] = _stats(
            key, key_hits[0].bias, counted, (base_up, base_down, int(base.size)), min_samples
        )
    return result


def _stats(
    key: PatternKey,
    bias: Bias,
    rets: list[float],
    base: tuple[float | None, float | None, int],
    min_samples: int,
) -> PatternStats:
    base_up, base_down, base_n = base
    n = len(rets)
    up_count = sum(1 for r in rets if r > 0)
    success: int | None = None
    hit_rate = low = high = base_rate = edge = None
    if bias is Bias.BULLISH:
        success = up_count
        base_rate = base_up
    elif bias is Bias.BEARISH:
        success = sum(1 for r in rets if r < 0)
        base_rate = base_down
    if success is not None and n > 0:
        hit_rate = success / n
        low, high = wilson_interval(success, n)
        if base_rate is not None:
            edge = hit_rate - base_rate
    return PatternStats(
        key=key,
        n=n,
        up_count=up_count,
        success_count=success,
        hit_rate=hit_rate,
        wilson_low=low,
        wilson_high=high,
        mean_return=statistics.fmean(rets) if rets else None,
        median_return=statistics.median(rets) if rets else None,
        base_up_rate=base_up,
        base_rate=base_rate,
        edge=edge,
        sufficient=n >= min_samples,
        base_down_rate=base_down,
        base_n=base_n,
    )
