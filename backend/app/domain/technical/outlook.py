"""One-week technical outlook: a transparent, weighted vote of simple signals.

This is a heuristic summary of what the indicators say today, NOT a forecast. Every signal
carries its direction, weight and a plain-English reason so the score can be audited.

score = sum(weight * direction) / sum(weight) over signals with weight > 0 (0 if none).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import pandas as pd

from app.domain.technical.candlesticks import PATTERNS, Bias, PatternHit, PatternKey
from app.domain.technical.indicators import atr, ema, macd, rsi
from app.domain.technical.reliability import PatternStats

Lean = Literal["bullish", "bearish", "neutral"]

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


@dataclass(frozen=True, slots=True)
class Signal:
    key: str
    label: str
    direction: int  # +1 bullish, 0 neutral, -1 bearish
    weight: float
    detail: str


@dataclass(frozen=True, slots=True)
class Outlook:
    as_of: datetime
    lean: Lean
    score: float  # in [-1, 1]
    signals: tuple[Signal, ...]
    expected_range: tuple[float, float] | None  # None while ATR is in warm-up
    last_close: float


def _pattern_signal(
    recent_hits: Sequence[PatternHit], reliability: Mapping[PatternKey, PatternStats]
) -> Signal:
    label = "Candlestick patterns"
    if not recent_hits:
        return Signal("patterns", label, 0, 0.0, "No candlestick patterns in the last 3 sessions.")
    signed: list[float] = []
    names: list[str] = []
    thin: list[str] = []
    for hit in recent_hits:
        name = PATTERNS[hit.key].label
        stats = reliability.get(hit.key)
        if stats is None or not stats.sufficient or stats.edge is None:
            thin.append(name)
            continue
        if stats.edge <= 0:
            continue
        sign = {Bias.BULLISH: 1, Bias.BEARISH: -1, Bias.NEUTRAL: 0}[hit.bias]
        signed.append(sign * min(stats.edge / EDGE_FULL_STRENGTH, 1.0))
        names.append(name)
    if not signed:
        if thin:
            detail = (
                f"{', '.join(thin)}: not enough past occurrences to judge reliability, "
                "so it is ignored."
            )
        else:
            detail = "Recent patterns have not beaten the base rate historically."
        return Signal("patterns", label, 0, 0.0, detail)
    mean = sum(signed) / len(signed)
    # weight * direction == mean signed strength, so opposing patterns offset one another.
    direction = 1 if mean > 0 else -1 if mean < 0 else 0
    detail = f"{', '.join(names)} historically beat the base rate on this stock."
    if thin:
        detail += f" Ignored for thin history: {', '.join(thin)}."
    return Signal("patterns", label, direction, abs(mean), detail)


def _rsi_signal(value: float) -> Signal:
    if value > _RSI_OVERBOUGHT:
        d, why = -1, "above 70 (overbought), which often precedes a pullback"
    elif value < _RSI_OVERSOLD:
        d, why = 1, "below 30 (oversold), which often precedes a bounce"
    else:
        d, why = 0, "between 30 and 70, so momentum is neither stretched up nor down"
    return Signal("rsi14", "RSI (14)", d, _W_RSI, f"RSI is {value:.0f}, {why}.")


def _ema_signal(fast: pd.Series, slow: pd.Series) -> Signal | None:
    diff = (fast - slow).to_numpy(dtype=float)
    now = diff[-1]
    if math.isnan(now):
        return None
    fresh = False
    for k in range(max(1, len(diff) - FRESH_CROSS_SESSIONS), len(diff)):
        if not math.isnan(diff[k - 1]) and (diff[k] > 0) != (diff[k - 1] > 0):
            fresh = True
    up = now > 0
    detail = (
        "9-day EMA is above the 21-day EMA" if up else "9-day EMA is at or below the 21-day EMA"
    )
    detail += (
        ", and the cross happened within the last 3 sessions."
        if fresh
        else ", with no fresh cross in the last 3 sessions."
    )
    return Signal("ema_cross", "EMA 9/21", 1 if up else -1, _W_EMA, detail)


def _macd_signal(hist: pd.Series) -> Signal | None:
    if len(hist) < _MIN_HIST:
        return None
    prev, now = float(hist.iloc[-2]), float(hist.iloc[-1])
    if math.isnan(prev) or math.isnan(now):
        return None
    rising = now > prev
    detail = (
        "MACD histogram is rising, so upward momentum is building."
        if rising
        else "MACD histogram is not rising, so momentum is fading or falling."
    )
    return Signal("macd_momentum", "MACD momentum", 1 if rising else -1, _W_MACD, detail)


def _vwap_signal(close: float, vwap_value: float) -> Signal:
    above = close > vwap_value
    detail = (
        f"Close {close:.2f} is above the 1-week VWAP {vwap_value:.2f}."
        if above
        else f"Close {close:.2f} is at or below the 1-week VWAP {vwap_value:.2f}."
    )
    return Signal("vwap", "Weekly VWAP", 1 if above else -1, _W_VWAP, detail)


def build_outlook(
    daily: pd.DataFrame,
    recent_hits: Sequence[PatternHit],
    reliability: Mapping[PatternKey, PatternStats],
    vwap_value: float | None,
    as_of: datetime,
) -> Outlook:
    """Combine indicator signals on completed daily bars into a lean and a score.

    ``recent_hits`` are the pattern hits of the last 3 sessions. Signals whose inputs are
    still in warm-up are omitted rather than guessed.
    """
    if daily.empty:
        raise ValueError("daily history is empty")
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
    if (s := _macd_signal(macd(close)["histogram"])) is not None:
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
