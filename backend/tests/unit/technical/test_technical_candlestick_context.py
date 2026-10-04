# ruff: noqa: RUF005
"""Candlestick trend/ATR context: patterns are judged on bars strictly before their first candle."""

import pandas as pd
from candle_fixtures import CTX_LEN, Bar, context, keys_at_last
from technical_refs import frame, trend_is

from app.domain.technical import PATTERNS, PatternKey, detect_patterns
from app.domain.technical.candlesticks import context_allows, trend_context

K = PatternKey


def test_detect_patterns_context_ignores_the_patterns_own_candles() -> None:
    # A huge gap-up hammer. If its own close (150) leaked into the trend test, sma10 would be
    # (9 * 84 + 150) / 10 = 90.6 > sma10 five bars earlier (88.5) and close > sma10, i.e. an
    # "uptrend": it would then be a hanging man. Context must come from bars before it only.
    df = frame(context("down") + [(140.0, 150.0, 100.0, 150.0)])

    last = {h.key for h in detect_patterns(df) if h.index == CTX_LEN}

    assert K.HAMMER in last
    assert K.HANGING_MAN not in last


def test_detect_patterns_multi_candle_context_ends_before_first_candle() -> None:
    # The same two candles are a bullish engulfing after the downtrend, but not when an up-spike
    # bar sits right before c1: the context is judged at the bar before c1 (close 99 > sma10,
    # while sma10 85.5 < sma10 five bars earlier 88.5 => no trend).
    spike: Bar = (80.0, 100.0, 79.0, 99.0)
    engulf = [(80.0, 80.5, 78.0, 78.5), (78.5, 80.5, 78.25, 80.25)]

    plain = {
        h.key for h in detect_patterns(frame(context("down") + engulf)) if h.index == CTX_LEN + 1
    }
    after_spike = {
        h.key
        for h in detect_patterns(frame(context("down") + [spike] + engulf))
        if h.index == CTX_LEN + 2
    }

    assert K.BULLISH_ENGULFING in plain
    assert K.BULLISH_ENGULFING not in after_spike


def test_detect_patterns_warmup_context_blocks_context_dependent_patterns() -> None:
    # only 8 bars: ATR(14) and sma10 are NaN, so nothing that needs them can fire.
    bars = context("down")[:7] + [(78.5, 79.0, 77.0, 79.0)]
    df = frame(bars)

    assert detect_patterns(df) == []


def test_detect_patterns_doji_needs_atr_but_not_trend() -> None:
    short_flat = context("flat")[:10] + [(100.0, 101.0, 99.0, 100.0)]

    assert detect_patterns(frame(short_flat)) == []
    assert K.DOJI in keys_at_last("flat", [(100.0, 101.0, 99.0, 100.0)])


def test_detect_patterns_soldiers_need_known_trend_even_when_atr_is_known() -> None:
    # 15 bars: ATR(14) is valid at idx 13 but sma10[p-5] is still NaN for the first candle.
    base = context("flat")[:14]
    soldiers = [
        (100.0, 101.75, 99.75, 101.5),
        (101.0, 102.75, 100.75, 102.5),
        (102.0, 103.75, 101.75, 103.5),
    ]

    assert detect_patterns(frame(base + soldiers)) == []


def test_trend_context_values_use_only_earlier_bars() -> None:
    df = frame([(100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i) for i in range(30)])
    changed = df.copy()
    changed.iloc[20, :4] = [500.0, 600.0, 400.0, 550.0]  # a spike at bar 20

    base, alt = trend_context(df), trend_context(changed)

    assert pd.isna(base.iloc[0])
    assert trend_is(base.iloc[25], "up")
    for s in range(21):  # context at s uses bars <= s-1, so bar 20 only affects s >= 21
        both_unknown = pd.isna(base.iloc[s]) and pd.isna(alt.iloc[s])
        assert both_unknown or base.iloc[s] == alt.iloc[s]


def test_pattern_specs_declare_their_required_trend_context() -> None:
    assert PATTERNS[K.DOJI].context == "any"
    assert PATTERNS[K.HAMMER].context == "down"
    assert PATTERNS[K.SHOOTING_STAR].context == "up"
    assert PATTERNS[K.THREE_WHITE_SOLDIERS].context == "down_or_none"
    assert PATTERNS[K.THREE_BLACK_CROWS].context == "up_or_none"
    assert context_allows("down_or_none", "none") is True
    assert context_allows("down_or_none", "up") is False
    assert context_allows("down", pd.NA) is False
    assert context_allows("any", pd.NA) is True
