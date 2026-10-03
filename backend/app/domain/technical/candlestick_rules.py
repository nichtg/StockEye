"""Candlestick shape and multi-candle rules: pure predicates over OHLC candles.

Detection, trend context and the pattern registry live in ``candlesticks``; this module holds
only the geometry so each rule can be read (and tuned via ``PatternThresholds``) in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PatternThresholds:
    atr_period: int = 14
    trend_sma_period: int = 10
    trend_lookback: int = 5  # sma10[s-1] is compared with sma10[s-1-lookback]
    long_body_atr: float = 0.5
    doji_body_range: float = 0.1
    doji_range_atr: float = 0.3
    shape_min_body_range: float = 0.1
    shape_tail_body_mult: float = 2.0
    shape_opposite_tail_range: float = 0.1
    engulf_body_atr: float = 0.3
    star_small_body: float = 0.3
    soldier_opposite_shadow_body: float = 0.3


@dataclass(frozen=True, slots=True)
class Candle:
    o: float
    h: float
    low: float
    c: float

    @property
    def body(self) -> float:
        return abs(self.c - self.o)

    @property
    def range(self) -> float:
        return self.h - self.low

    @property
    def upper(self) -> float:
        return self.h - max(self.o, self.c)

    @property
    def lower(self) -> float:
        return min(self.o, self.c) - self.low

    @property
    def bull(self) -> bool:
        return self.c > self.o

    @property
    def bear(self) -> bool:
        return self.c < self.o

    @property
    def mid(self) -> float:
        return (self.o + self.c) / 2.0


@dataclass(frozen=True, slots=True)
class Ctx:
    trend: int | None  # +1 up, -1 down, 0 none, None unknown (warm-up)
    atr: float  # NaN in warm-up


def hammer_shape(c: Candle, t: PatternThresholds) -> bool:
    return (
        c.body > t.shape_min_body_range * c.range
        and c.lower >= t.shape_tail_body_mult * c.body
        and c.upper <= t.shape_opposite_tail_range * c.range
    )


def inverted_shape(c: Candle, t: PatternThresholds) -> bool:
    return (
        c.body > t.shape_min_body_range * c.range
        and c.upper >= t.shape_tail_body_mult * c.body
        and c.lower <= t.shape_opposite_tail_range * c.range
    )


def is_long(c: Candle, ctx: Ctx, t: PatternThresholds) -> bool:
    return c.body >= t.long_body_atr * ctx.atr  # False when ATR is NaN


def bull_engulf(a: Candle, b: Candle, ctx: Ctx, t: PatternThresholds) -> bool:
    return (
        a.bear
        and b.bull
        and b.o <= a.c
        and b.c >= a.o
        and b.body > a.body
        and b.body >= t.engulf_body_atr * ctx.atr
    )


def bear_engulf(a: Candle, b: Candle, ctx: Ctx, t: PatternThresholds) -> bool:
    return (
        a.bull
        and b.bear
        and b.o >= a.c
        and b.c <= a.o
        and b.body > a.body
        and b.body >= t.engulf_body_atr * ctx.atr
    )


def bull_harami(a: Candle, b: Candle, ctx: Ctx, t: PatternThresholds) -> bool:
    return (
        a.bear
        and is_long(a, ctx, t)
        and b.bull
        and max(b.o, b.c) <= a.o
        and min(b.o, b.c) >= a.c
        and b.body < a.body
    )


def bear_harami(a: Candle, b: Candle, ctx: Ctx, t: PatternThresholds) -> bool:
    return (
        a.bull
        and is_long(a, ctx, t)
        and b.bear
        and max(b.o, b.c) <= a.c
        and min(b.o, b.c) >= a.o
        and b.body < a.body
    )


def piercing(a: Candle, b: Candle, ctx: Ctx, t: PatternThresholds) -> bool:
    return a.bear and is_long(a, ctx, t) and b.bull and b.o <= a.c and a.mid < b.c < a.o


def dark_cloud(a: Candle, b: Candle, ctx: Ctx, t: PatternThresholds) -> bool:
    return a.bull and is_long(a, ctx, t) and b.bear and b.o >= a.c and a.o < b.c < a.mid


def morning_star(a: Candle, b: Candle, c: Candle, ctx: Ctx, t: PatternThresholds) -> bool:
    return (
        a.bear
        and is_long(a, ctx, t)
        and b.body <= t.star_small_body * a.body
        and b.mid < a.c
        and c.bull
        and c.c > a.mid
    )


def evening_star(a: Candle, b: Candle, c: Candle, ctx: Ctx, t: PatternThresholds) -> bool:
    return (
        a.bull
        and is_long(a, ctx, t)
        and b.body <= t.star_small_body * a.body
        and b.mid > a.c
        and c.bear
        and c.c < a.mid
    )


def soldiers(a: Candle, b: Candle, c: Candle, ctx: Ctx, t: PatternThresholds) -> bool:
    cs = (a, b, c)
    for i, x in enumerate(cs):
        if not (
            x.bull and is_long(x, ctx, t) and x.upper <= t.soldier_opposite_shadow_body * x.body
        ):
            return False
        if i > 0:
            p = cs[i - 1]
            if not (x.c > p.c and p.o <= x.o <= p.c):
                return False
    return True


def crows(a: Candle, b: Candle, c: Candle, ctx: Ctx, t: PatternThresholds) -> bool:
    cs = (a, b, c)
    for i, x in enumerate(cs):
        if not (
            x.bear and is_long(x, ctx, t) and x.lower <= t.soldier_opposite_shadow_body * x.body
        ):
            return False
        if i > 0:
            p = cs[i - 1]
            if not (x.c < p.c and p.c <= x.o <= p.o):
                return False
    return True
