"""Candlestick pattern detection with trend and volatility context.

Context (trend, ATR) for a pattern whose first candle is at position ``s`` uses only bars
``<= s - 1``, so the pattern's own candles never decide whether it is a reversal. Where the
context is still in warm-up (NaN), patterns that need it cannot fire; that includes the
"down or none" three-soldiers rule, which needs a *known* trend.

All numeric thresholds live in ``PatternThresholds``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

import numpy as np
import pandas as pd

from app.domain.technical.candlestick_rules import (
    Candle,
    Ctx,
    PatternThresholds,
    bear_engulf,
    bear_harami,
    bull_engulf,
    bull_harami,
    crows,
    dark_cloud,
    evening_star,
    hammer_shape,
    inverted_shape,
    morning_star,
    piercing,
    soldiers,
)
from app.domain.technical.indicators import _validate_ohlcv, atr, sma


class Bias(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class PatternKey(StrEnum):
    DOJI = "doji"
    HAMMER = "hammer"
    HANGING_MAN = "hanging_man"
    INVERTED_HAMMER = "inverted_hammer"
    SHOOTING_STAR = "shooting_star"
    BULLISH_ENGULFING = "bullish_engulfing"
    BEARISH_ENGULFING = "bearish_engulfing"
    BULLISH_HARAMI = "bullish_harami"
    BEARISH_HARAMI = "bearish_harami"
    PIERCING_LINE = "piercing_line"
    DARK_CLOUD_COVER = "dark_cloud_cover"
    MORNING_STAR = "morning_star"
    EVENING_STAR = "evening_star"
    THREE_WHITE_SOLDIERS = "three_white_soldiers"
    THREE_BLACK_CROWS = "three_black_crows"


# Trend context a pattern requires before its first candle ("none" = no clear trend).
TrendNeed = Literal["any", "up", "down", "up_or_none", "down_or_none"]
Trend = Literal["up", "down", "none"]

_ALLOWED: Mapping[TrendNeed, frozenset[str]] = MappingProxyType(
    {
        "any": frozenset({"up", "down", "none"}),
        "up": frozenset({"up"}),
        "down": frozenset({"down"}),
        "up_or_none": frozenset({"up", "none"}),
        "down_or_none": frozenset({"down", "none"}),
    }
)


def context_allows(need: TrendNeed, trend: object) -> bool:
    """Whether a trend-context value (``"up"``/``"down"``/``"none"``/NA) satisfies ``need``.

    ``"any"`` accepts everything, including unknown (warm-up) context; every other
    requirement needs a *known* trend.
    """
    if need == "any":
        return True
    return isinstance(trend, str) and trend in _ALLOWED[need]


@dataclass(frozen=True, slots=True)
class PatternSpec:
    key: PatternKey
    label: str
    bias: Bias
    candles: int
    context: TrendNeed = "any"


def _specs() -> dict[PatternKey, PatternSpec]:
    k, b = PatternKey, Bias
    rows: list[tuple[PatternKey, str, Bias, int, TrendNeed]] = [
        (k.DOJI, "Doji", b.NEUTRAL, 1, "any"),
        (k.HAMMER, "Hammer", b.BULLISH, 1, "down"),
        (k.HANGING_MAN, "Hanging man", b.BEARISH, 1, "up"),
        (k.INVERTED_HAMMER, "Inverted hammer", b.BULLISH, 1, "down"),
        (k.SHOOTING_STAR, "Shooting star", b.BEARISH, 1, "up"),
        (k.BULLISH_ENGULFING, "Bullish engulfing", b.BULLISH, 2, "down"),
        (k.BEARISH_ENGULFING, "Bearish engulfing", b.BEARISH, 2, "up"),
        (k.BULLISH_HARAMI, "Bullish harami", b.BULLISH, 2, "down"),
        (k.BEARISH_HARAMI, "Bearish harami", b.BEARISH, 2, "up"),
        (k.PIERCING_LINE, "Piercing line", b.BULLISH, 2, "down"),
        (k.DARK_CLOUD_COVER, "Dark cloud cover", b.BEARISH, 2, "up"),
        (k.MORNING_STAR, "Morning star", b.BULLISH, 3, "down"),
        (k.EVENING_STAR, "Evening star", b.BEARISH, 3, "up"),
        (k.THREE_WHITE_SOLDIERS, "Three white soldiers", b.BULLISH, 3, "down_or_none"),
        (k.THREE_BLACK_CROWS, "Three black crows", b.BEARISH, 3, "up_or_none"),
    ]
    return {key: PatternSpec(key, label, bias, n, ctx) for key, label, bias, n, ctx in rows}


PATTERNS: Mapping[PatternKey, PatternSpec] = MappingProxyType(_specs())


@dataclass(frozen=True, slots=True)
class PatternHit:
    key: PatternKey
    bias: Bias
    index: int  # integer position of the pattern's LAST candle
    date: datetime  # index label of that candle


DEFAULT_THRESHOLDS = PatternThresholds()

_UP, _DOWN = 1, -1
_THREE_SPAN = 3


def _trend_ok(ctx: Ctx, wanted: int, *, allow_none: bool = False) -> bool:
    if ctx.trend is None:
        return False
    return ctx.trend == wanted or (allow_none and ctx.trend == 0)


_TwoRule = Callable[[Candle, Candle, Ctx, PatternThresholds], bool]
_ThreeRule = Callable[[Candle, Candle, Candle, Ctx, PatternThresholds], bool]

_TWO: tuple[tuple[PatternKey, int, _TwoRule], ...] = (
    (PatternKey.BULLISH_ENGULFING, _DOWN, bull_engulf),
    (PatternKey.BEARISH_ENGULFING, _UP, bear_engulf),
    (PatternKey.BULLISH_HARAMI, _DOWN, bull_harami),
    (PatternKey.BEARISH_HARAMI, _UP, bear_harami),
    (PatternKey.PIERCING_LINE, _DOWN, piercing),
    (PatternKey.DARK_CLOUD_COVER, _UP, dark_cloud),
)
# (key, required trend, accept unknown-free "none" trend too, rule)
_THREE: tuple[tuple[PatternKey, int, bool, _ThreeRule], ...] = (
    (PatternKey.MORNING_STAR, _DOWN, False, morning_star),
    (PatternKey.EVENING_STAR, _UP, False, evening_star),
    (PatternKey.THREE_WHITE_SOLDIERS, _DOWN, True, soldiers),
    (PatternKey.THREE_BLACK_CROWS, _UP, True, crows),
)


def _evaluate_at(
    cs: list[Candle], ctxs: list[Ctx], t: int, th: PatternThresholds
) -> list[PatternKey]:
    """Patterns whose last candle is at ``t``; context is taken before each first candle."""
    hits: list[PatternKey] = []
    k = PatternKey
    last = cs[t]

    # One-candle patterns: the first candle is ``t`` itself, so context is bars <= t-1.
    ctx = ctxs[t]
    if (
        last.range > 0
        and last.body <= th.doji_body_range * last.range
        and last.range >= th.doji_range_atr * ctx.atr
    ):
        hits.append(k.DOJI)
    if hammer_shape(last, th):
        if _trend_ok(ctx, _DOWN):
            hits.append(k.HAMMER)
        if _trend_ok(ctx, _UP):
            hits.append(k.HANGING_MAN)
    if inverted_shape(last, th):
        if _trend_ok(ctx, _DOWN):
            hits.append(k.INVERTED_HAMMER)
        if _trend_ok(ctx, _UP):
            hits.append(k.SHOOTING_STAR)

    if t >= 1:
        ctx = ctxs[t - 1]
        hits.extend(
            key
            for key, want, rule in _TWO
            if _trend_ok(ctx, want) and rule(cs[t - 1], last, ctx, th)
        )

    if t >= _THREE_SPAN - 1:
        ctx = ctxs[t - 2]
        hits.extend(
            key
            for key, want, allow_none, rule in _THREE
            if _trend_ok(ctx, want, allow_none=allow_none)
            and rule(cs[t - 2], cs[t - 1], last, ctx, th)
        )
    return hits


def trend_context(
    df: pd.DataFrame, thresholds: PatternThresholds = DEFAULT_THRESHOLDS
) -> pd.Series:
    """Trend before each bar, as an object Series of ``"up"``/``"down"``/``"none"``/NA.

    The value at position ``s`` is the context for a pattern whose first candle is ``s``: it
    uses only bars ``<= s - 1`` (uptrend: close > sma10 and sma10 rising over 5 bars; downtrend
    is the mirror). NA while the moving average is still in warm-up, and at position 0.
    """
    th = thresholds
    close = df["close"].astype(float)
    ma = sma(close, th.trend_sma_period).to_numpy(dtype=float)
    cl = close.to_numpy(dtype=float)
    out: list[object] = [pd.NA] * len(df)
    for s in range(1, len(df)):
        p = s - 1
        then_i = p - th.trend_lookback
        now = ma[p]
        then = ma[then_i] if then_i >= 0 else np.nan
        if np.isnan(now) or np.isnan(then):
            continue
        if cl[p] > now > then:
            out[s] = "up"
        elif cl[p] < now < then:
            out[s] = "down"
        else:
            out[s] = "none"
    return pd.Series(out, index=df.index, dtype=object)


_TREND_INT: Mapping[str, int] = MappingProxyType({"up": _UP, "down": _DOWN, "none": 0})


def _contexts(df: pd.DataFrame, th: PatternThresholds) -> list[Ctx]:
    """``ctxs[s]`` is the context for a pattern whose first candle is ``s``: bars ``<= s-1``."""
    trend = trend_context(df, th).to_numpy(dtype=object)
    atr_v = atr(df, th.atr_period).to_numpy(dtype=float)
    nan = float("nan")
    return [
        Ctx(
            _TREND_INT[trend[s]] if isinstance(trend[s], str) else None,
            float(atr_v[s - 1]) if s > 0 else nan,
        )
        for s in range(len(df))
    ]


def detect_patterns(
    df: pd.DataFrame, thresholds: PatternThresholds = DEFAULT_THRESHOLDS
) -> list[PatternHit]:
    """Detect all patterns on every bar of ``df`` (completed bars, increasing index).

    A hit's ``index`` is the position of the pattern's last candle; its trend/ATR context uses
    only bars strictly before the pattern's first candle. Sorted by index, then registry order.
    Raises ``ValueError`` on NaN prices or a non-increasing index.
    """
    _validate_ohlcv(df)
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    cs = [Candle(float(o[i]), float(h[i]), float(low[i]), float(c[i])) for i in range(len(df))]
    ctxs = _contexts(df, thresholds)
    hits: list[PatternHit] = []
    for t in range(len(df)):
        stamp = pd.Timestamp(df.index[t]).to_pydatetime()
        hits.extend(
            PatternHit(key, PATTERNS[key].bias, t, stamp)
            for key in _evaluate_at(cs, ctxs, t, thresholds)
        )
    return hits
