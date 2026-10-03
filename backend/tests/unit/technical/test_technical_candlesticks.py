# ruff: noqa: RUF005
"""Candlestick tests on hand-built fixtures.

Every fixture starts with 20 context bars whose true range is exactly 2.0, so ATR(14) == 2.0
at the last context bar and "long" means body >= 1.0, "engulf" min body is 0.6.

Context kinds (bar i = 0..19):
  down: open = 100 - i, close = open - 1  -> last close 80, sma10 falling  => downtrend
  up:   open = 100 + i, close = open + 1  -> last close 120, sma10 rising  => uptrend
  flat: alternating 100->101 / 101->100   -> last close 100, sma10 constant => no trend
Prices that sit on a threshold are multiples of 0.25 so they are exact in binary floating point.
"""

from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from technical_refs import frame, ohlc_frames

from app.domain.technical import PATTERNS, PatternHit, PatternKey, PatternThresholds
from app.domain.technical import detect_patterns as detect
from app.domain.technical.candlesticks import Bias

Bar = tuple[float, float, float, float]  # open, high, low, close
K = PatternKey
CTX_LEN = 20


def context(kind: str) -> list[Bar]:
    bars: list[Bar] = []
    for i in range(CTX_LEN):
        if kind == "down":
            o = 100.0 - i
            bars.append((o, o + 0.5, o - 1.5, o - 1.0))
        elif kind == "up":
            o = 100.0 + i
            bars.append((o, o + 1.5, o - 0.5, o + 1.0))
        else:
            o, c = (100.0, 101.0) if i % 2 == 0 else (101.0, 100.0)
            bars.append((o, max(o, c) + 0.5, min(o, c) - 0.5, c))
    return bars


def keys_at_last(kind: str, pattern: list[Bar]) -> set[PatternKey]:
    df = frame(context(kind) + pattern)
    last = len(df) - 1
    return {h.key for h in detect(df) if h.index == last}


# (id, context, candles, expected key)
POSITIVE: list[tuple[str, str, list[Bar], PatternKey]] = [
    ("hammer", "down", [(78.5, 79.0, 77.0, 79.0)], K.HAMMER),
    ("hanging_man", "up", [(121.0, 121.5, 119.5, 121.5)], K.HANGING_MAN),
    ("inverted_hammer", "down", [(79.0, 81.0, 79.0, 79.5)], K.INVERTED_HAMMER),
    ("shooting_star", "up", [(121.0, 123.0, 121.0, 121.5)], K.SHOOTING_STAR),
    (
        "bullish_engulfing",
        "down",
        [(80.0, 80.5, 78.0, 78.5), (78.5, 80.5, 78.25, 80.25)],
        K.BULLISH_ENGULFING,
    ),
    (
        "bearish_engulfing",
        "up",
        [(120.0, 122.0, 119.75, 121.5), (121.5, 121.75, 119.5, 119.75)],
        K.BEARISH_ENGULFING,
    ),
    (
        "bullish_harami",
        "down",
        [(80.0, 80.5, 77.0, 77.5), (78.0, 79.25, 77.75, 79.0)],
        K.BULLISH_HARAMI,
    ),
    (
        "bearish_harami",
        "up",
        [(120.0, 123.0, 119.5, 122.5), (122.0, 122.25, 120.5, 121.0)],
        K.BEARISH_HARAMI,
    ),
    (
        "piercing_line",
        "down",
        [(80.0, 80.5, 77.0, 77.5), (77.0, 79.25, 76.75, 79.0)],
        K.PIERCING_LINE,
    ),
    (
        "dark_cloud_cover",
        "up",
        [(120.0, 123.0, 119.5, 122.5), (123.0, 123.25, 120.75, 121.0)],
        K.DARK_CLOUD_COVER,
    ),
    (
        "morning_star",
        "down",
        [(80.0, 80.5, 77.0, 77.5), (77.0, 77.75, 76.75, 77.5), (77.5, 79.25, 77.25, 79.0)],
        K.MORNING_STAR,
    ),
    (
        "evening_star",
        "up",
        [
            (120.0, 123.0, 119.5, 122.5),
            (122.75, 123.5, 122.5, 123.25),
            (123.0, 123.25, 120.75, 121.0),
        ],
        K.EVENING_STAR,
    ),
    ("doji_flat", "flat", [(100.0, 101.0, 99.0, 100.0625)], K.DOJI),
    ("doji_down", "down", [(78.0, 79.0, 77.0, 78.0625)], K.DOJI),
    (
        "soldiers_flat",
        "flat",
        [
            (100.0, 101.75, 99.75, 101.5),
            (101.0, 102.75, 100.75, 102.5),
            (102.0, 103.75, 101.75, 103.5),
        ],
        K.THREE_WHITE_SOLDIERS,
    ),
    (
        "soldiers_down",
        "down",
        [(80.0, 81.75, 79.75, 81.5), (81.0, 82.75, 80.75, 82.5), (82.0, 83.75, 81.75, 83.5)],
        K.THREE_WHITE_SOLDIERS,
    ),
    (
        "crows_flat",
        "flat",
        [(100.0, 100.25, 98.25, 98.5), (99.0, 99.25, 97.25, 97.5), (98.0, 98.25, 96.25, 96.5)],
        K.THREE_BLACK_CROWS,
    ),
    (
        "crows_up",
        "up",
        [
            (120.0, 120.25, 118.25, 118.5),
            (119.0, 119.25, 117.25, 117.5),
            (118.0, 118.25, 116.25, 116.5),
        ],
        K.THREE_BLACK_CROWS,
    ),
]

# Near misses: each is one tick away from satisfying the rule.
NEGATIVE: list[tuple[str, str, list[Bar], PatternKey]] = [
    # lower shadow 0.9 < 2 * body (1.0)
    ("hammer_short_tail", "down", [(78.5, 79.0, 77.6, 79.0)], K.HAMMER),
    # perfect hammer shape, but in an uptrend it is a hanging man, not a hammer
    ("hammer_in_uptrend", "up", [(120.5, 121.0, 119.0, 121.0)], K.HAMMER),
    # perfect hammer shape in a flat market has no reversal context
    ("hammer_no_trend", "flat", [(99.5, 100.0, 98.0, 100.0)], K.HAMMER),
    # upper shadow 0.5 > 10% of the 2.5 range
    ("hammer_big_upper", "down", [(78.5, 79.5, 77.0, 79.0)], K.HAMMER),
    ("hanging_man_in_downtrend", "down", [(78.5, 79.0, 77.0, 79.0)], K.HANGING_MAN),
    # upper shadow 0.75 < 2 * body (1.0)
    ("inverted_hammer_short_tail", "down", [(79.0, 80.25, 79.0, 79.5)], K.INVERTED_HAMMER),
    ("shooting_star_in_downtrend", "down", [(79.0, 81.0, 79.0, 79.5)], K.SHOOTING_STAR),
    # c2 closes at 79.75: engulfs only the prior body's close, not its open (80)
    (
        "bullish_engulfing_close_inside",
        "down",
        [(80.0, 80.5, 78.0, 78.5), (78.5, 80.0, 78.25, 79.75)],
        K.BULLISH_ENGULFING,
    ),
    # bodies equal (1.5 vs 1.5): needs strictly larger
    (
        "bullish_engulfing_equal_bodies",
        "down",
        [(80.0, 80.5, 78.0, 78.5), (78.5, 80.25, 78.25, 80.0)],
        K.BULLISH_ENGULFING,
    ),
    # c2 opens one tick above c1 close (gap up open): not engulfing
    (
        "bullish_engulfing_open_above_prior_close",
        "down",
        [(80.0, 80.5, 78.0, 78.5), (78.75, 80.75, 78.5, 80.75)],
        K.BULLISH_ENGULFING,
    ),
    # c2 body 0.3 < 0.3 * ATR (0.6) although it engulfs the tiny first body
    (
        "bullish_engulfing_too_small_for_atr",
        "down",
        [(80.0, 80.25, 79.5, 79.875), (79.75, 80.25, 79.5, 80.0625)],
        K.BULLISH_ENGULFING,
    ),
    (
        "bullish_engulfing_in_uptrend",
        "up",
        [(120.0, 120.5, 118.0, 118.5), (118.5, 120.5, 118.25, 120.25)],
        K.BULLISH_ENGULFING,
    ),
    (
        "bearish_engulfing_close_inside",
        "up",
        [(120.0, 122.0, 119.75, 121.5), (121.5, 121.75, 120.0, 120.25)],
        K.BEARISH_ENGULFING,
    ),
    (
        "bearish_engulfing_in_downtrend",
        "down",
        [(80.0, 82.0, 79.75, 81.5), (81.5, 81.75, 79.5, 79.75)],
        K.BEARISH_ENGULFING,
    ),
    # c2 reaches above o1 (80.25 > 80): not inside the first body
    (
        "bullish_harami_exceeds_body",
        "down",
        [(80.0, 80.5, 77.0, 77.5), (78.0, 80.5, 77.75, 80.25)],
        K.BULLISH_HARAMI,
    ),
    # first candle not long: body 0.5 < 0.5 * ATR (1.0)
    (
        "bullish_harami_first_not_long",
        "down",
        [(80.0, 80.25, 79.25, 79.5), (79.625, 79.875, 79.5, 79.75)],
        K.BULLISH_HARAMI,
    ),
    # c2 is bearish, not bullish
    (
        "bullish_harami_second_bearish",
        "down",
        [(80.0, 80.5, 77.0, 77.5), (79.0, 79.25, 77.75, 78.0)],
        K.BULLISH_HARAMI,
    ),
    (
        "bearish_harami_exceeds_body",
        "up",
        [(120.0, 123.0, 119.5, 122.5), (122.0, 122.25, 119.75, 119.75)],
        K.BEARISH_HARAMI,
    ),
    # closes exactly at the midpoint 78.75: must be strictly above
    (
        "piercing_line_at_midpoint",
        "down",
        [(80.0, 80.5, 77.0, 77.5), (77.0, 78.75, 76.75, 78.75)],
        K.PIERCING_LINE,
    ),
    # closes at o1 (80): that is not < o1, it is a full reversal
    (
        "piercing_line_closes_at_prior_open",
        "down",
        [(80.0, 80.5, 77.0, 77.5), (77.0, 80.25, 76.75, 80.0)],
        K.PIERCING_LINE,
    ),
    (
        "dark_cloud_at_midpoint",
        "up",
        [(120.0, 123.0, 119.5, 122.5), (123.0, 123.25, 121.0, 121.25)],
        K.DARK_CLOUD_COVER,
    ),
    (
        "dark_cloud_closes_at_prior_open",
        "up",
        [(120.0, 123.0, 119.5, 122.5), (123.0, 123.25, 119.75, 120.0)],
        K.DARK_CLOUD_COVER,
    ),
    # third close exactly at the first candle's midpoint 78.75
    (
        "morning_star_close_at_midpoint",
        "down",
        [(80.0, 80.5, 77.0, 77.5), (77.0, 77.75, 76.75, 77.5), (77.5, 78.75, 77.25, 78.75)],
        K.MORNING_STAR,
    ),
    # star midpoint 77.5 equals c1 close: must be strictly below
    (
        "morning_star_star_not_below_close",
        "down",
        [(80.0, 80.5, 77.0, 77.5), (77.25, 77.75, 77.0, 77.75), (77.5, 79.25, 77.25, 79.0)],
        K.MORNING_STAR,
    ),
    # star body 1.0 > 0.3 * 2.5
    (
        "morning_star_big_middle",
        "down",
        [(80.0, 80.5, 77.0, 77.5), (76.5, 77.75, 76.25, 77.5), (77.5, 79.25, 77.25, 79.0)],
        K.MORNING_STAR,
    ),
    (
        "evening_star_close_at_midpoint",
        "up",
        [
            (120.0, 123.0, 119.5, 122.5),
            (122.75, 123.5, 122.5, 123.25),
            (123.0, 123.25, 121.25, 121.25),
        ],
        K.EVENING_STAR,
    ),
    # c3 open sits below c2 open (101 < 101 is false at 100.75): outside the previous body
    (
        "soldiers_open_outside_prior_body",
        "flat",
        [
            (100.0, 101.75, 99.75, 101.5),
            (101.0, 102.75, 100.75, 102.5),
            (100.75, 103.75, 100.5, 103.5),
        ],
        K.THREE_WHITE_SOLDIERS,
    ),
    # c3 upper shadow 0.8 > 0.3 * body (1.5)
    (
        "soldiers_long_upper_shadow",
        "flat",
        [
            (100.0, 101.75, 99.75, 101.5),
            (101.0, 102.75, 100.75, 102.5),
            (102.0, 104.3, 101.75, 103.5),
        ],
        K.THREE_WHITE_SOLDIERS,
    ),
    # c3 body 0.75 < 0.5 * ATR (1.0)
    (
        "soldiers_small_third_body",
        "flat",
        [
            (100.0, 101.75, 99.75, 101.5),
            (101.0, 102.75, 100.75, 102.5),
            (102.0, 102.9, 101.75, 102.75),
        ],
        K.THREE_WHITE_SOLDIERS,
    ),
    # c3 does not close above c2
    (
        "soldiers_close_not_higher",
        "flat",
        [
            (100.0, 101.75, 99.75, 101.5),
            (101.0, 102.75, 100.75, 102.5),
            (101.5, 102.75, 101.25, 102.5),
        ],
        K.THREE_WHITE_SOLDIERS,
    ),
    # a bullish run after an uptrend is exhaustion, not a soldiers continuation
    (
        "soldiers_in_uptrend",
        "up",
        [
            (120.0, 121.75, 119.75, 121.5),
            (121.0, 122.75, 120.75, 122.5),
            (122.0, 123.75, 121.75, 123.5),
        ],
        K.THREE_WHITE_SOLDIERS,
    ),
    (
        "crows_open_outside_prior_body",
        "flat",
        [(100.0, 100.25, 98.25, 98.5), (99.0, 99.25, 97.25, 97.5), (99.25, 99.5, 96.25, 96.5)],
        K.THREE_BLACK_CROWS,
    ),
    (
        "crows_in_downtrend",
        "down",
        [(80.0, 80.25, 78.25, 78.5), (79.0, 79.25, 77.25, 77.5), (78.0, 78.25, 76.25, 76.5)],
        K.THREE_BLACK_CROWS,
    ),
    # range 0.5 < 0.3 * ATR (0.6)
    ("doji_too_small_for_atr", "flat", [(100.0, 100.25, 99.75, 100.0)], K.DOJI),
    # body 0.3 > 10% of the 1.9 range
    ("doji_body_too_big", "flat", [(100.0, 101.0, 99.0, 100.3)], K.DOJI),
    ("doji_zero_range", "flat", [(100.0, 100.0, 100.0, 100.0)], K.DOJI),
]


@pytest.mark.parametrize(("case", "kind", "pattern", "key"), POSITIVE, ids=[p[0] for p in POSITIVE])
def test_detect_patterns_positive_fixture_fires_on_last_candle(
    case: str, kind: str, pattern: list[Bar], key: PatternKey
) -> None:
    df = frame(context(kind) + pattern)

    hits = [h for h in detect(df) if h.key is key]

    assert [h.index for h in hits] == [len(df) - 1], case
    assert hits[0].date == df.index[-1]
    assert hits[0].bias is PATTERNS[key].bias


@pytest.mark.parametrize(("case", "kind", "pattern", "key"), NEGATIVE, ids=[n[0] for n in NEGATIVE])
def test_detect_patterns_near_miss_fixture_does_not_fire(
    case: str, kind: str, pattern: list[Bar], key: PatternKey
) -> None:
    assert key not in keys_at_last(kind, pattern), case


def test_detect_patterns_only_pattern_bars_fire_in_context_bars() -> None:
    df = frame(context("down") + [(78.5, 79.0, 77.0, 79.0)])

    assert all(h.index >= CTX_LEN for h in detect(df) if h.key is not K.DOJI)


def test_detect_patterns_hits_sorted_by_index_with_several_on_one_bar() -> None:
    # Second bar is both a bullish harami (inside a long bearish bar) and hammer-shaped
    # (body 0.5, lower shadow 1.0, no upper shadow).
    bars = [(80.0, 80.5, 77.0, 77.5), (77.75, 78.25, 76.75, 78.25)]
    df = frame(context("down") + bars + [(100.0, 101.0, 99.0, 100.0)])

    hits = detect(df)

    at_21 = {h.key for h in hits if h.index == CTX_LEN + 1}
    assert {K.HAMMER, K.BULLISH_HARAMI} <= at_21
    assert [h.index for h in hits] == sorted(h.index for h in hits)


def test_detect_patterns_context_ignores_the_patterns_own_candles() -> None:
    # A huge gap-up hammer. If its own close (150) leaked into the trend test, sma10 would be
    # (9 * 84 + 150) / 10 = 90.6 > sma10 five bars earlier (88.5) and close > sma10, i.e. an
    # "uptrend": it would then be a hanging man. Context must come from bars before it only.
    df = frame(context("down") + [(140.0, 150.0, 100.0, 150.0)])

    last = {h.key for h in detect(df) if h.index == CTX_LEN}

    assert K.HAMMER in last
    assert K.HANGING_MAN not in last


def test_detect_patterns_multi_candle_context_ends_before_first_candle() -> None:
    # The same two candles are a bullish engulfing after the downtrend, but not when an up-spike
    # bar sits right before c1: the context is judged at the bar before c1 (close 99 > sma10,
    # while sma10 85.5 < sma10 five bars earlier 88.5 => no trend).
    spike: Bar = (80.0, 100.0, 79.0, 99.0)
    engulf = [(80.0, 80.5, 78.0, 78.5), (78.5, 80.5, 78.25, 80.25)]

    plain = {h.key for h in detect(frame(context("down") + engulf)) if h.index == CTX_LEN + 1}
    after_spike = {
        h.key for h in detect(frame(context("down") + [spike] + engulf)) if h.index == CTX_LEN + 2
    }

    assert K.BULLISH_ENGULFING in plain
    assert K.BULLISH_ENGULFING not in after_spike


def test_detect_patterns_warmup_context_blocks_context_dependent_patterns() -> None:
    # only 8 bars: ATR(14) and sma10 are NaN, so nothing that needs them can fire.
    bars = context("down")[:7] + [(78.5, 79.0, 77.0, 79.0)]
    df = frame(bars)

    assert detect(df) == []


def test_detect_patterns_doji_needs_atr_but_not_trend() -> None:
    short_flat = context("flat")[:10] + [(100.0, 101.0, 99.0, 100.0)]

    assert detect(frame(short_flat)) == []
    assert K.DOJI in keys_at_last("flat", [(100.0, 101.0, 99.0, 100.0)])


def test_detect_patterns_soldiers_need_known_trend_even_when_atr_is_known() -> None:
    # 15 bars: ATR(14) is valid at idx 13 but sma10[p-5] is still NaN for the first candle.
    base = context("flat")[:14]
    soldiers = [
        (100.0, 101.75, 99.75, 101.5),
        (101.0, 102.75, 100.75, 102.5),
        (102.0, 103.75, 101.75, 103.5),
    ]

    assert detect(frame(base + soldiers)) == []


def test_detect_patterns_custom_thresholds_change_outcome() -> None:
    bars = [(80.0, 80.25, 79.25, 79.5), (79.625, 79.875, 79.5, 79.75)]
    df = frame(context("down") + bars)

    default = {h.key for h in detect(df) if h.index == CTX_LEN + 1}
    relaxed = {
        h.key for h in detect(df, PatternThresholds(long_body_atr=0.2)) if h.index == CTX_LEN + 1
    }

    assert K.BULLISH_HARAMI not in default
    assert K.BULLISH_HARAMI in relaxed


def test_detect_patterns_prefix_of_history_gives_same_hits() -> None:
    bars = context("down") + [
        (80.0, 80.5, 78.0, 78.5),
        (78.5, 80.5, 78.25, 80.25),
        (80.0, 81.0, 79.0, 80.0),
    ]
    full = detect(frame(bars))

    prefix = detect(frame(bars[:-1]))

    assert prefix == [h for h in full if h.index < len(bars) - 1]


@settings(max_examples=40, deadline=None)
@given(df=ohlc_frames(min_size=25, max_size=50))
def test_detect_patterns_property_future_bars_never_change_earlier_hits(df: pd.DataFrame) -> None:
    k = len(df) - 5
    changed = df.copy()
    changed.loc[changed.index[k:], ["open", "high", "low", "close"]] = np.tile(
        [50.0, 90.0, 10.0, 70.0], (len(df) - k, 1)
    )

    before = [h for h in detect(df) if h.index < k]
    after = [h for h in detect(changed) if h.index < k]

    assert before == after


def test_patterns_registry_covers_all_keys_with_labels_and_bias() -> None:
    assert set(PATTERNS) == set(PatternKey)
    assert PATTERNS[K.BULLISH_ENGULFING].label == "Bullish engulfing"
    assert PATTERNS[K.BULLISH_ENGULFING].bias is Bias.BULLISH
    assert PATTERNS[K.DOJI].bias is Bias.NEUTRAL
    assert PATTERNS[K.EVENING_STAR].bias is Bias.BEARISH
    assert {k: s.candles for k, s in PATTERNS.items() if s.candles == 3} == {
        K.MORNING_STAR: 3,
        K.EVENING_STAR: 3,
        K.THREE_WHITE_SOLDIERS: 3,
        K.THREE_BLACK_CROWS: 3,
    }
    assert all(1 <= s.candles <= 3 for s in PATTERNS.values())


def test_pattern_hit_and_spec_are_frozen() -> None:
    hit = PatternHit(K.DOJI, Bias.NEUTRAL, 3, pd.Timestamp("2024-01-04").to_pydatetime())

    with pytest.raises(FrozenInstanceError):
        hit.index = 4  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        PATTERNS[K.DOJI].label = "x"  # type: ignore[misc]
