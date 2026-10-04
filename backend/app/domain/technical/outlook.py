"""One-week technical outlook: a transparent, weighted vote of simple signals.

This is a heuristic summary of what the indicators say today, NOT a forecast. Every signal
carries its direction, weight and a plain-English reason so the score can be audited.

score = sum(weight * direction) / sum(weight) over signals with weight > 0 (0 if none).

Ties (EMAs equal, close equal to VWAP, MACD histogram unchanged) give direction 0 but the
signal keeps its weight, so a flat market pulls the score towards neutral instead of being
read as bearish.

Pattern rule: a recent pattern counts only if its history is sufficient AND the Wilson lower
bound of its success rate exceeds the matching conditional base rate (it is credibly better
than a typical week in the same trend). Strength = min((hit_rate - base_rate) / 0.2, 1); the
signal is the mean of signed strengths. Doji and other neutral patterns carry no direction.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import pandas as pd

from app.domain.technical.candlesticks import PATTERNS, Bias, PatternHit, PatternKey
from app.domain.technical.indicators import _validate_ohlcv, atr, ema, macd, rsi
from app.domain.technical.reliability import PatternStats

Lean = Literal["bullish", "bearish", "neutral"]
Direction = Literal[-1, 0, 1]

LEAN_THRESHOLD = 0.25
EDGE_FULL_STRENGTH = 0.2
RANGE_SESSIONS = 5  # 1 week of trading sessions
FRESH_CROSS_SESSIONS = 3

_RSI_OVERBOUGHT = 70
_RSI_OVERSOLD = 30
_MIN_HIST = 2
_W_RSI = 0.75
_W_EMA = 0.75
_W_VWAP = 0.5
_W_MACD = 0.5
_TIE_REL = 1e-9  # relative tolerance below which two prices/indicators count as equal


@dataclass(frozen=True, slots=True)
class Signal:
    key: str
    label: str
    direction: Direction  # +1 bullish, 0 neutral, -1 bearish
    weight: float
    detail: str


@dataclass(frozen=True, slots=True)
class Outlook:
    as_of: datetime
    lean: Lean
    score: float  # in [-1, 1]
    signals: tuple[Signal, ...]
    # Typical 1-week range (about 9 in 10 weeks fall inside): last_close +/- ATR14 * sqrt(5).
    # None while ATR is in warm-up. Not a forecast or a confidence interval.
    expected_range: tuple[float, float] | None
    last_close: float
    # Coverage measured in the fix-round-1 logic audit simulation of 1-week ranges.
    expected_range_coverage: float = 0.9

    @property
    def typical_week_range(self) -> tuple[float, float] | None:
        """Alias of ``expected_range``: the typical 1-week range (about 9 in 10 weeks inside)."""
        return self.expected_range


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _pattern_line(hit: PatternHit, stats: PatternStats | None) -> tuple[float | None, str]:
    """(signed strength if the pattern counts, plain-English sentence) for one recent hit."""
    name = PATTERNS[hit.key].label
    if hit.bias is Bias.NEUTRAL:
        return None, f"{name}: indecision pattern, no directional signal"
    if stats is None or not stats.sufficient:
        seen = 0 if stats is None else stats.n
        return None, (
            f"{name}: not enough past occurrences to judge reliability "
            f"(seen {seen} times), so it is ignored"
        )
    if stats.hit_rate is None or stats.base_rate is None or stats.success_count is None:
        return None, f"{name}: no comparable typical week to judge it against, so it is ignored"
    word = "higher" if hit.bias is Bias.BULLISH else "lower"
    credible = stats.wilson_low is not None and stats.wilson_low > stats.base_rate
    if not credible:
        return None, (
            f"{name} has been seen {stats.n} times, but not clearly better than a typical week"
        )
    sign = 1 if hit.bias is Bias.BULLISH else -1
    strength = min((stats.hit_rate - stats.base_rate) / EDGE_FULL_STRENGTH, 1.0)
    return sign * strength, (
        f"{name} has been reliable for this stock ({word} a week later "
        f"{stats.success_count} of {stats.n} times vs {_pct(stats.base_rate)} normally)"
    )


def _pattern_signal(
    recent_hits: Sequence[PatternHit], reliability: Mapping[PatternKey, PatternStats]
) -> Signal:
    """Patterns count only when sufficient AND credibly (Wilson low bound) above their base rate.

    Requiring more than a positive point estimate keeps a lucky 9-of-15 streak from moving the
    score; the Wilson bound accounts for how few samples a one-stock history provides.
    """
    label = "Candlestick patterns"
    if not recent_hits:
        return Signal(
            "patterns", label, 0, 0.0, "No candlestick patterns in the last 3 trading days."
        )
    signed: list[float] = []
    lines: list[str] = []
    for hit in recent_hits:
        strength, line = _pattern_line(hit, reliability.get(hit.key))
        lines.append(line)
        if strength is not None:
            signed.append(strength)
    detail = "; ".join(lines) + "."
    if not signed:
        return Signal("patterns", label, 0, 0.0, detail)
    mean = sum(signed) / len(signed)
    # weight * direction == mean signed strength, so opposing patterns offset one another.
    return Signal("patterns", label, _sign(mean, 0.0), abs(mean), detail)


def _rsi_signal(value: float) -> Signal:
    d: Direction
    if value > _RSI_OVERBOUGHT:
        d, why = -1, "above 70 (overbought), which often precedes a pullback"
    elif value < _RSI_OVERSOLD:
        d, why = 1, "below 30 (oversold), which often precedes a bounce"
    else:
        d, why = 0, "between 30 and 70, so momentum is neither stretched up nor down"
    return Signal("rsi14", "RSI (14)", d, _W_RSI, f"RSI is {value:.1f}, {why}.")


def _tie_tolerance(scale: float) -> float:
    """Differences below this are float noise, i.e. a tie (constant prices give exact ties)."""
    return _TIE_REL * max(abs(scale), 1.0)


def _sign(x: float, tol: float) -> Direction:
    return 0 if abs(x) <= tol else 1 if x > 0 else -1


def _ema_signal(fast: pd.Series, slow: pd.Series) -> Signal | None:
    diff = (fast - slow).to_numpy(dtype=float)
    now = diff[-1]
    if math.isnan(now):
        return None
    tol = _tie_tolerance(float(slow.iloc[-1]))
    fresh = False
    for k in range(max(1, len(diff) - FRESH_CROSS_SESSIONS), len(diff)):
        if not math.isnan(diff[k - 1]) and _sign(diff[k], tol) != _sign(diff[k - 1], tol):
            fresh = True
    d = _sign(now, tol)
    detail = {
        1: "9-day EMA is above the 21-day EMA",
        0: "9-day EMA equals the 21-day EMA",
        -1: "9-day EMA is below the 21-day EMA",
    }[d]
    detail += (
        ", and the cross happened within the last 3 trading days."
        if fresh
        else ", with no fresh cross in the last 3 trading days."
    )
    return Signal("ema_cross", "EMA 9/21", d, _W_EMA, detail)


def _macd_signal(hist: pd.Series, scale: float) -> Signal | None:
    if len(hist) < _MIN_HIST:
        return None
    prev, now = float(hist.iloc[-2]), float(hist.iloc[-1])
    if math.isnan(prev) or math.isnan(now):
        return None
    d = _sign(now - prev, _tie_tolerance(scale))
    detail = {
        1: "MACD histogram is rising, so upward momentum is building.",
        0: "MACD histogram is unchanged, so momentum is steady.",
        -1: "MACD histogram is falling, so momentum is fading or reversing.",
    }[d]
    return Signal("macd_momentum", "MACD momentum", d, _W_MACD, detail)


def _vwap_signal(close: float, vwap_value: float) -> Signal:
    d = _sign(close - vwap_value, _tie_tolerance(vwap_value))
    detail = {
        1: f"Close {close:.2f} is above the 1-week VWAP {vwap_value:.2f}.",
        0: f"Close {close:.2f} is at the 1-week VWAP {vwap_value:.2f}.",
        -1: f"Close {close:.2f} is below the 1-week VWAP {vwap_value:.2f}.",
    }[d]
    return Signal("vwap", "Weekly VWAP", d, _W_VWAP, detail)


def build_outlook(
    daily: pd.DataFrame,
    recent_hits: Sequence[PatternHit],
    reliability: Mapping[PatternKey, PatternStats],
    vwap_value: float | None,
    as_of: datetime,
) -> Outlook:
    """Combine indicator signals on completed daily bars into a lean and a score.

    ``recent_hits`` are the pattern hits of the last 3 trading days. Signals whose inputs are
    still in warm-up are omitted rather than guessed.
    """
    if daily.empty:
        raise ValueError("daily history is empty")
    _validate_ohlcv(daily)
    close = daily["close"].astype(float)
    last_close = float(close.iloc[-1])

    signals: list[Signal] = [_pattern_signal(recent_hits, reliability)]
    rsi_now = float(rsi(close, 14).iloc[-1])
    if not math.isnan(rsi_now):
        signals.append(_rsi_signal(rsi_now))
    if (s := _ema_signal(ema(close, 9), ema(close, 21))) is not None:
        signals.append(s)
    if vwap_value is not None:
        signals.append(_vwap_signal(last_close, vwap_value))
    if (s := _macd_signal(macd(close)["histogram"], last_close)) is not None:
        signals.append(s)

    total = sum(s.weight for s in signals if s.weight > 0)
    score = sum(s.weight * s.direction for s in signals) / total if total > 0 else 0.0
    lean: Lean = (
        "bullish"
        if score >= LEAN_THRESHOLD
        else "bearish"
        if score <= -LEAN_THRESHOLD
        else "neutral"
    )

    atr_now = float(atr(daily, 14).iloc[-1])
    expected: tuple[float, float] | None = None
    if not math.isnan(atr_now):
        spread = atr_now * math.sqrt(RANGE_SESSIONS)
        expected = (last_close - spread, last_close + spread)
    return Outlook(as_of, lean, score, tuple(signals), expected, last_close)
