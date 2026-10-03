"""Historical reliability of candlestick patterns on a single instrument.

Forward return for a hit at position ``t``: enter at ``open[t+1]`` (the next session's open,
the first price one could actually trade), exit at ``close[t+horizon]``. Hits whose exit bar
does not exist are dropped. Per pattern key, hits are made non-overlapping: a hit is skipped
when ``t - last_counted < horizon`` (its holding window would overlap the previous one).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.domain.technical.candlesticks import Bias, PatternHit, PatternKey


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
    base_up_rate: float | None
    base_rate: float | None
    edge: float | None
    sufficient: bool


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
    min_samples: int = 8,
) -> dict[PatternKey, PatternStats]:
    """Per-pattern forward-return statistics for every key present in ``hits``.

    ``base_up_rate`` is the share of all eligible bars in ``df`` with a positive forward
    return; ``edge`` is the pattern's success rate minus the matching base rate.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    rets = _forward_returns(df, horizon)
    eligible = rets[~np.isnan(rets)]
    base_up = float((eligible > 0).mean()) if eligible.size else None

    by_key: dict[PatternKey, list[PatternHit]] = {}
    for hit in sorted(hits, key=lambda h: h.index):
        by_key.setdefault(hit.key, []).append(hit)

    result: dict[PatternKey, PatternStats] = {}
    for key, key_hits in by_key.items():
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
        result[key] = _stats(key, key_hits[0].bias, counted, base_up, min_samples)
    return result


def _stats(
    key: PatternKey, bias: Bias, rets: list[float], base_up: float | None, min_samples: int
) -> PatternStats:
    n = len(rets)
    up_count = sum(1 for r in rets if r > 0)
    success: int | None = None
    hit_rate = low = high = base_rate = edge = None
    if bias is Bias.BULLISH:
        success = up_count
        base_rate = base_up
    elif bias is Bias.BEARISH:
        success = sum(1 for r in rets if r < 0)
        base_rate = None if base_up is None else 1.0 - base_up
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
    )
